import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.contracts import DesignSpec, Measurement, Session, State
from backend.main import create_app
from backend.storage import RevisionConflict, SessionStore
from backend.workflow import transition


def fixture(track="adapt"):
    return json.loads(
        (
            __import__("pathlib").Path("sample_data")
            / f"{track}_example/design_spec.json"
        ).read_text()
    )


@pytest.mark.parametrize("track", ["adapt", "repair"])
def test_persistence_across_restart(tmp_path, track):
    app = create_app(tmp_path / "db.sqlite3")
    with TestClient(app) as client:
        response = client.post("/api/sessions", json={"track": track, "consent": True})
        assert response.status_code == 201
        saved = response.json()
        assert saved["state"] == "created"
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        assert client.get(f"/api/sessions/{saved['id']}").json() == saved
        assert client.get(f"/api/sessions/{uuid4()}").status_code == 404
        assert client.get("/api/sessions/not-a-uuid").status_code == 422
        assert isinstance(client.get("/api/health").json()["capabilities"]["cad"], bool)


def test_consent_and_unknown_fields(tmp_path):
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        for body in (
            {"track": "adapt"},
            {"track": "repair", "consent": False},
            {"track": "adapt", "consent": True, "state": "ready"},
        ):
            assert client.post("/api/sessions", json=body).status_code == 422


def test_transition_and_concurrency(tmp_path):
    store = SessionStore(tmp_path / "db.sqlite3")
    session = store.create(Session(track="adapt", consent=True))
    with pytest.raises(ValueError):
        transition(session, State.READY)
    with pytest.raises(ValueError):
        transition(session, State.NEEDS_INFO)
    next_session = transition(session, State.ANALYZING)
    store.save(next_session, expected_revision=0)
    with pytest.raises(RevisionConflict):
        store.save(next_session, expected_revision=0)
    recovering = transition(
        next_session, State.NEEDS_INFO, reason="Retake the photo in better light"
    )
    assert recovering.pending_reason
    assert transition(recovering, State.ANALYZING).pending_reason is None


@pytest.mark.parametrize("track", ["adapt", "repair"])
def test_contract_fixtures_and_hash(track):
    spec = DesignSpec.model_validate(fixture(track))
    assert spec.example
    assert (
        spec.model_copy(
            update={"created_at": spec.created_at.replace(year=2020)}
        ).content_hash()
        == spec.content_hash()
    )
    assert (
        spec.model_copy(update={"difficulty": "Changed need"}).content_hash()
        != spec.content_hash()
    )
    schema = json.loads(
        __import__("pathlib").Path("schemas/design-spec-v1.schema.json").read_text()
    )
    assert schema == DesignSpec.model_json_schema()


@pytest.mark.parametrize("track", ["adapt", "repair"])
def test_verification_cannot_exceed_evidence(track):
    data = fixture(track)
    data["verification_level"] = "physically_verified"
    with pytest.raises(ValidationError):
        DesignSpec.model_validate(data)
    data["verification_level"] = "dimensionally_estimated"
    data["measurements"] = {}
    with pytest.raises(ValidationError):
        DesignSpec.model_validate(data)


@pytest.mark.parametrize(
    "track,key", [("adapt", "inner_width_mm"), ("repair", "hole_spacing_mm")]
)
def test_parameter_measurement_consistency(track, key):
    data = fixture(track)
    data["parameters"][key] += 1
    with pytest.raises(ValidationError):
        DesignSpec.model_validate(data)


@pytest.mark.parametrize(
    "data",
    [
        {"status": "estimated", "value_mm": 12, "sigma_mm": 0},
        {
            "status": "estimated",
            "value_mm": float("nan"),
            "sigma_mm": 1,
            "sources": ["manual_ruler"],
        },
        {
            "status": "cross_checked",
            "value_mm": 12,
            "sigma_mm": 1,
            "sources": ["manual_ruler", "manual_ruler"],
        },
        {
            "status": "physically_verified",
            "value_mm": 12,
            "sigma_mm": 1,
            "sources": ["photo_on_sheet"],
            "confirmed_by_user": True,
        },
    ],
)
def test_measurement_evidence(data):
    with pytest.raises(ValidationError):
        Measurement.model_validate(data)
