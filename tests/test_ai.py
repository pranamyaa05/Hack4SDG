import base64
import json
import threading

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.ai.models import VisionAnalysis
from backend.ai.providers import AISettings
from backend.ai.questions import extract_explicit_difficulty
from backend.main import create_app
from backend.measurement.fit_sheet import render_sheet

VALID = dict(
    object_type="spoon",
    component="handle",
    cross_section_guess="oval",
    handle_end_side="bottom",
    confidence="medium",
    visible_facts=["A utensil is visible."],
    inferences=["The handle may be oval."],
    suggested_difficulty="unknown",
)


def transport(handler=None):
    def default(request):
        return httpx.Response(
            200, json={"done": True, "message": {"content": json.dumps(VALID)}}
        )

    return httpx.MockTransport(handler or default)


def create(client, track="adapt"):
    return client.post("/api/sessions", json={"track": track, "consent": True}).json()[
        "id"
    ]


def upload(client, sid, revision=0, notes=""):
    encoded = cv2.imencode(".png", render_sheet())[1].tobytes()
    return client.post(
        f"/api/sessions/{sid}/image",
        files={"image": ("fixture.png", encoded, "image/png")},
        data={"expected_revision": revision, "user_text": notes},
    )


def confirm(client, sid, revision, track="adapt", **extra):
    return client.post(
        f"/api/sessions/{sid}/confirm-object",
        json=dict(
            expected_revision=revision,
            object_type="spoon" if track == "adapt" else "drawer_handle",
            component="handle" if track == "adapt" else "drawer_mounting_holes",
            cross_section="oval",
            handle_intact=True,
            confirmed_by_user=True,
            **extra,
        ),
    )


def test_local_pipeline_and_measurement_gate(tmp_path):
    app = create_app(tmp_path / "db", ai_transport=transport())
    with TestClient(app) as client:
        sid = create(client)
        uploaded = upload(client, sid, notes="It slips")
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["workspace"]["answers"]["difficulty"] == "slipping"
        analyzed = client.post(
            f"/api/sessions/{sid}/analyze", json={"expected_revision": 1}
        )
        assert analyzed.status_code == 200, analyzed.text
        data = analyzed.json()
        assert data["revision"] == 3
        assert data["support"]["status"] == "needs_confirmation"
        assert data["workspace"]["analysis"] == VALID
        assert (
            client.post(
                f"/api/sessions/{sid}/measurement/start",
                json={"expected_revision": 3, "mode": "manual"},
            ).status_code
            == 409
        )
        confirmed = confirm(client, sid, 3).json()
        assert [q["id"] for q in confirmed["questions"]] == ["material_preference"]
        answered = client.post(
            f"/api/sessions/{sid}/answers",
            json={"expected_revision": 4, "material_preference": "soft"},
        )
        assert answered.json()["support"]["status"] == "supported"
        assert (
            client.post(
                f"/api/sessions/{sid}/measurement/start",
                json={"expected_revision": 5, "mode": "manual"},
            ).status_code
            == 200
        )
        assert upload(client, sid, revision=6).status_code == 409
    with TestClient(
        create_app(tmp_path / "db", ai_settings=AISettings(provider="manual"))
    ) as client:
        data = client.get(f"/api/sessions/{sid}/analysis").json()
        assert data["workspace"]["answers"]["material_preference"] == "soft"
        assert data["workspace"]["analysis"] == VALID


@pytest.mark.parametrize("track", ["adapt", "repair"])
def test_manual_no_inference_path(tmp_path, track):
    def must_not_call(request):
        pytest.fail("Manual path must not send inference requests")

    with TestClient(
        create_app(tmp_path / "db", ai_transport=transport(must_not_call))
    ) as client:
        sid = create(client, track)
        response = confirm(client, sid, 0, track)
        assert response.status_code == 200, response.text
        assert response.json()["workspace"]["provider"] == "manual"
        assert len(response.json()["questions"]) == 2
        fields = (
            dict(difficulty="pain", material_preference="no_preference")
            if track == "adapt"
            else dict(
                repair_case="missing_pull_visible_holes", surface_condition="sound"
            )
        )
        response = client.post(
            f"/api/sessions/{sid}/answers", json=dict(expected_revision=1, **fields)
        )
        assert response.json()["support"]["status"] == "supported"


@pytest.mark.parametrize("bad", [{"object_type": "toothbrush"}, {"dimension_mm": 14}])
def test_schema_rejects_unknown_objects_and_dimensions(bad):
    with pytest.raises(ValidationError):
        VisionAnalysis.model_validate({**VALID, **bad})


def test_invalid_response_retries_once_then_manual(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"done": True, "message": {"content": "not json"}}
        )

    with TestClient(
        create_app(tmp_path / "db", ai_transport=transport(handler))
    ) as client:
        sid = create(client)
        upload(client, sid)
        response = client.post(
            f"/api/sessions/{sid}/analyze", json={"expected_revision": 1}
        )
        assert response.status_code == 200, response.text
        assert response.json()["workspace"]["provider_status"] == "invalid_response"
        assert response.json()["workspace"]["analysis"] is None
        assert len(calls) == 2


def test_unavailable_provider_does_not_repeat_or_expose_error(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="secret-provider-body")

    with TestClient(
        create_app(tmp_path / "db", ai_transport=transport(handler))
    ) as client:
        sid = create(client)
        upload(client, sid)
        response = client.post(
            f"/api/sessions/{sid}/analyze", json={"expected_revision": 1}
        )
        assert response.status_code == 200
        assert response.json()["workspace"]["provider_status"] == "unavailable"
        assert "secret-provider-body" not in response.text
        assert len(calls) == 1


def test_cloud_consent_and_request_shape(tmp_path):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "test-secret"
        assert (
            payload["generationConfig"]["responseJsonSchema"]["additionalProperties"]
            is False
        )
        image = base64.b64decode(
            payload["contents"][0]["parts"][1]["inlineData"]["data"]
        )
        decoded = cv2.imdecode(np.frombuffer(image, np.uint8), 1)
        assert max(decoded.shape[:2]) == 768
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps(VALID)}]},
                    }
                ]
            },
        )

    settings = AISettings(
        provider="gemini",
        gemini_model="configured-test-model",
        gemini_api_key="test-secret",
    )
    with TestClient(
        create_app(
            tmp_path / "db", ai_settings=settings, ai_transport=transport(handler)
        )
    ) as client:
        sid = create(client)
        upload(client, sid)
        denied = client.post(
            f"/api/sessions/{sid}/analyze", json={"expected_revision": 1}
        )
        assert denied.status_code == 422 and not calls
        response = client.post(
            f"/api/sessions/{sid}/analyze",
            json={"expected_revision": 1, "cloud_consent": True},
        )
        assert response.status_code == 200, response.text
        assert len(calls) == 1
        assert "test-secret" not in response.text
        assert "test-secret" not in client.get("/api/ai/providers").text
        assert "test-secret" not in repr(settings)


@pytest.mark.parametrize(
    "fields",
    [
        dict(object_type="other", component="handle", handle_intact=True),
        dict(object_type="spoon", component="other", handle_intact=True),
        dict(object_type="spoon", component="handle", handle_intact=False),
    ],
)
def test_unsupported_adapt_declined(tmp_path, fields):
    with TestClient(create_app(tmp_path / "db")) as client:
        sid = create(client)
        response = client.post(
            f"/api/sessions/{sid}/confirm-object",
            json=dict(
                expected_revision=0,
                cross_section="unknown",
                confirmed_by_user=True,
                **fields,
            ),
        )
        assert response.json()["support"]["status"] == "unsupported"
        assert (
            client.post(
                f"/api/sessions/{sid}/measurement/start",
                json=dict(expected_revision=1, mode="manual"),
            ).status_code
            == 409
        )


def test_hidden_repair_declined(tmp_path):
    with TestClient(create_app(tmp_path / "db")) as client:
        sid = create(client, "repair")
        confirm(client, sid, 0, "repair")
        response = client.post(
            f"/api/sessions/{sid}/answers",
            json=dict(expected_revision=1, repair_case="hidden_mounting"),
        )
        assert response.json()["support"]["status"] == "unsupported"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("It slips", "slipping"),
        ("It does not slip", None),
        ("It slips and hurts", None),
        ("I cannot wrap my fingers", "cannot_wrap_fingers"),
        ("My grip is weak", "weak_grip"),
        ("arthritis", None),
    ],
)
def test_explicit_text_rules(text, expected):
    assert extract_explicit_difficulty(text) == expected


def test_stale_updates_and_cancellation_cannot_overwrite(tmp_path):
    entered = threading.Event()
    finish = threading.Event()
    results = []

    def handler(request):
        entered.set()
        assert finish.wait(5)
        return httpx.Response(
            200, json={"done": True, "message": {"content": json.dumps(VALID)}}
        )

    with TestClient(
        create_app(tmp_path / "db", ai_transport=transport(handler))
    ) as client:
        sid = create(client)
        upload(client, sid)

        def run():
            results.append(
                client.post(
                    f"/api/sessions/{sid}/analyze", json={"expected_revision": 1}
                )
            )

        thread = threading.Thread(target=run)
        thread.start()
        assert entered.wait(5)
        try:
            response = client.post(
                f"/api/sessions/{sid}/analysis/cancel", json={"expected_revision": 2}
            )
            assert response.status_code == 200, response.text
        finally:
            finish.set()
            thread.join(5)
        assert results[0].status_code == 409
        assert (
            client.get(f"/api/sessions/{sid}/analysis").json()["workspace"][
                "provider_status"
            ]
            == "interrupted"
        )


def test_bad_quality_does_not_change_session(tmp_path):
    with TestClient(create_app(tmp_path / "db")) as client:
        sid = create(client)
        data = cv2.imencode(".png", np.full((1600, 1000, 3), 166, np.uint8))[
            1
        ].tobytes()
        response = client.post(
            f"/api/sessions/{sid}/image",
            files={"image": ("blank.png", data, "image/png")},
            data={"expected_revision": 0},
        )
        assert response.status_code == 422
        assert client.get(f"/api/sessions/{sid}").json()["revision"] == 0


def test_malformed_gemini_envelope_falls_back(tmp_path):
    settings = AISettings(
        provider="gemini", gemini_model="test-model", gemini_api_key="test-key"
    )
    mock = transport(lambda request: httpx.Response(200, json={"candidates": [None]}))
    with TestClient(
        create_app(tmp_path / "db", ai_settings=settings, ai_transport=mock)
    ) as client:
        sid = create(client)
        upload(client, sid)
        response = client.post(
            f"/api/sessions/{sid}/analyze",
            json={"expected_revision": 1, "cloud_consent": True},
        )
        assert response.status_code == 200
        assert response.json()["workspace"]["provider_status"] == "invalid_response"
        assert response.json()["workspace"]["analysis"] is None


def test_revised_ambiguous_notes_do_not_keep_old_keyword_answer(tmp_path):
    with TestClient(
        create_app(tmp_path / "db", ai_settings=AISettings(provider="manual"))
    ) as client:
        sid = create(client)
        upload(client, sid, notes="It slips")
        response = client.post(
            f"/api/sessions/{sid}/analyze",
            json={"expected_revision": 1, "user_text": "It does not slip"},
        )
        assert response.status_code == 200
        assert response.json()["workspace"]["answers"]["difficulty"] is None
