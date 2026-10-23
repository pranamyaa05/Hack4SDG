import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.ai.providers import AISettings
from backend.design.models import ManufacturingSpec
from backend.design.package import build_package
from backend.main import create_app


def fixture_spec(track="adapt"):
    data = json.loads(Path(f"sample_data/{track}_example/design_spec.json").read_text())
    data.update(
        schema_version="1.1.0",
        variant="balanced",
        material="TPU" if track == "adapt" else "PETG",
        cross_section="oval",
    )
    if track == "repair":
        data["parameters"]["bar_width_mm"] = 12
        data["mounting"] = dict(
            bolt_diameter_mm=3,
            face_thickness_mm=16,
            bolt_length_mm=70,
            nut_height_mm=3,
            confirmed_by_user=True,
        )
    return ManufacturingSpec.model_validate(data)


@pytest.mark.parametrize("track", ["adapt", "repair"])
def test_real_cad_package_and_checksums(tmp_path, track):
    spec = fixture_spec(track)
    record = build_package(spec, tmp_path)
    folder = tmp_path / spec.design_id
    manifest = json.loads((folder / "manifest.json").read_text())
    for file, digest in manifest["artifact_sha256"].items():
        assert hashlib.sha256((folder / file).read_bytes()).hexdigest() == digest
    assert record["metrics"]["watertight"] is True
    assert record["metrics"]["volume_mm3"] > 0
    assert (folder / "part.step").stat().st_size > 1000
    assert (folder / "part.stl").stat().st_size > 1000
    assert (folder / "build_card.pdf").read_bytes().startswith(b"%PDF")
    with zipfile.ZipFile(folder / "package.zip") as archive:
        assert "manifest.json" in archive.namelist()
        assert "part.step" in archive.namelist()
        assert "package.zip" not in archive.namelist()


def ready_session(client, track):
    sid = client.post("/api/sessions", json=dict(track=track, consent=True)).json()[
        "id"
    ]
    root = f"/api/sessions/{sid}"
    response = client.post(
        root + "/confirm-object",
        json=dict(
            expected_revision=0,
            object_type="spoon" if track == "adapt" else "drawer_handle",
            component="handle" if track == "adapt" else "drawer_mounting_holes",
            cross_section="oval",
            handle_intact=True,
            confirmed_by_user=True,
        ),
    )
    assert response.status_code == 200, response.text
    fields = (
        dict(difficulty="weak_grip", material_preference="soft")
        if track == "adapt"
        else dict(repair_case="missing_pull_visible_holes", surface_condition="sound")
    )
    response = client.post(root + "/answers", json=dict(expected_revision=1, **fields))
    assert response.status_code == 200, response.text
    response = client.post(
        root + "/measurement/start", json=dict(expected_revision=2, mode="manual")
    )
    assert response.status_code == 200, response.text
    values = (
        {"handle_width": 14, "handle_thickness": 7, "covered_length": 90}
        if track == "adapt"
        else {"hole_spacing": 96, "hole_diameter": 4}
    )
    revision = 3
    for dimension, value in values.items():
        response = client.post(
            root + "/measurements/manual",
            json=dict(
                expected_revision=revision,
                dimension=dimension,
                value_mm=value,
                instrument="manual_caliper",
                resolution_mm=0.05,
                confirmed_by_user=True,
            ),
        )
        assert response.status_code == 200, response.text
        revision += 1
    return sid, revision


def test_complete_api_download_refit_feedback_statistics(tmp_path):
    with TestClient(
        create_app(tmp_path / "db", ai_settings=AISettings(provider="manual"))
    ) as client:
        assert client.get("/api/statistics").json()["designs_generated"] == 0
        sid, revision = ready_session(client, "adapt")
        options = client.get(f"/api/sessions/{sid}/recommendations")
        assert options.status_code == 200, options.text
        response = client.post(
            f"/api/sessions/{sid}/generate",
            json=dict(expected_revision=revision, variant="balanced", material="TPU"),
        )
        assert response.status_code == 201, response.text
        design = response.json()["design"]
        did = design["id"]
        download = client.get(f"/api/designs/{did}/package.zip")
        assert download.status_code == 200
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert json.loads(archive.read("design_spec.json"))["design_id"] == did
        assert (
            client.post(
                f"/api/designs/{did}/feedback",
                json=dict(
                    outcome="too_tight", kept_in_use=True, confirmed_by_user=True
                ),
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/designs/{did}/feedback",
                json=dict(outcome="fits", kept_in_use=True, confirmed_by_user=True),
            ).status_code
            == 200
        )
        stats = client.get("/api/statistics").json()
        assert stats["reported_items_kept_in_use"] == 1
        assert stats["reported_fit_trials"] == 1
        assert stats["solid_material_estimate_g"] > 0
        refit = client.post(f"/api/designs/{did}/refit", json=dict(consent=True))
        assert refit.status_code == 201, refit.text
        assert refit.json()["session"]["id"] != sid
        assert refit.json()["parent_design_id"] == did
        assert client.get(f"/api/designs/{did}").json()["spec"] == design["spec"]
        assert client.get(f"/api/designs/{did}/files/not-a-file.txt").status_code == 404


def test_repair_mounting_gate_and_generation(tmp_path):
    with TestClient(create_app(tmp_path / "db")) as client:
        sid, revision = ready_session(client, "repair")
        url = f"/api/sessions/{sid}/generate"
        body = dict(expected_revision=revision, variant="balanced", material="PETG")
        assert client.post(url, json=body).status_code == 422
        body["mounting"] = dict(
            bolt_diameter_mm=3,
            face_thickness_mm=16,
            bolt_length_mm=70,
            nut_height_mm=3,
            confirmed_by_user=True,
        )
        response = client.post(url, json=body)
        assert response.status_code == 201, response.text
        assert response.json()["design"]["spec"]["track"] == "repair"


def test_manufacturing_gates():
    from pydantic import ValidationError

    spec = fixture_spec()
    with pytest.raises(ValidationError):
        ManufacturingSpec.model_validate(dict(spec.model_dump(), material="PLA"))
    repair = fixture_spec("repair").model_dump()
    repair["mounting"]["bolt_length_mm"] = 10
    with pytest.raises(ValidationError):
        ManufacturingSpec.model_validate(repair)


def test_flat_corner_wall_and_round_shape_gates():
    from pydantic import ValidationError

    data = fixture_spec().model_dump()
    data["cross_section"] = "round"
    with pytest.raises(ValidationError, match="round cross-section"):
        ManufacturingSpec.model_validate(data)
    data = fixture_spec().model_dump()
    data["cross_section"] = "flat"
    data["parameters"]["outer_width_mm"] = 20
    data["parameters"]["outer_thickness_mm"] = 20
    with pytest.raises(ValidationError, match="minimum-wall"):
        ManufacturingSpec.model_validate(data)


def test_manufacturing_schema_snapshot():
    assert (
        json.loads(
            Path("schemas/manufacturing-spec-v1.1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        == ManufacturingSpec.model_json_schema()
    )
