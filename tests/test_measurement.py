import math
from io import BytesIO

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import create_app
from backend.measurement.fit_sheet import (
    MM_TO_PT,
    fit_sheet_pdf,
    render_sheet,
)
from backend.measurement.metrology import (
    add_observation,
    ellipse_perimeter,
    perimeter_observation,
    solve_thickness,
)
from backend.measurement.models import (
    HoleRequest,
    Observation,
    PerimeterRequest,
    RegionRequest,
    Workspace,
)
from backend.measurement.vision import (
    calibrate,
    decode_image,
    hole_measurement,
    project,
    region_measurements,
)


def obs(
    value, method="manual_ruler", sigma=0.5, dimension="handle_width", evidence="a"
):
    return Observation(
        dimension=dimension,
        value_mm=value,
        sigma_mm=sigma,
        method=method,
        evidence_ids=[evidence],
        confirmed_by_user=True,
    )


def png(image):
    return cv2.imencode(".png", image)[1].tobytes()


@pytest.fixture(scope="module")
def calibrated():
    image = render_sheet()
    return calibrate(image, scale_check_passed=True)


def test_perspective_recovery_and_roundtrip():
    image = render_sheet()
    h = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [2099, 0], [2099, 2969], [0, 2969]]),
        np.float32([[100, 150], [2050, 50], [1950, 2800], [200, 2900]]),
    )
    warped = cv2.warpPerspective(image, h, (2200, 3000), borderValue=(255, 255, 255))
    result, rectified = calibrate(warped, scale_check_passed=True)
    assert result.marker_ids == [0, 1, 2, 3]
    assert result.reprojection_rms_mm < 0.2
    points = np.array([[60, 60], [150, 150], [90, 190]], float)
    recovered = project(project(points * 10, h), np.array(result.homography))
    assert np.max(np.linalg.norm(recovered - points, axis=1)) < 0.2
    assert rectified.shape == (2970, 2100, 3)


def test_scale_confirmation_and_missing_markers():
    with pytest.raises(ValueError, match="scale-check"):
        calibrate(render_sheet(), scale_check_passed=False)
    image = render_sheet()
    image[:450] = 255
    with pytest.raises(ValueError, match="three"):
        calibrate(image, scale_check_passed=True)


def test_warped_sheet_rejected():
    image = render_sheet()
    marker = image[120:420, 120:420].copy()
    image[120:420, 120:420] = 255
    image[170:470, 160:460] = marker
    with pytest.raises(ValueError, match="disagree"):
        calibrate(image, scale_check_passed=True)


def test_three_markers(calibrated):
    image = render_sheet()
    image[2550:2850, 1680:1980] = 255
    calibration, _ = calibrate(image, scale_check_passed=True)
    assert len(calibration.marker_ids) == 3
    request = HoleRequest(
        expected_revision=0,
        calibration_id=calibration.id,
        first={"x_mm": 170, "y_mm": 230},
        second={"x_mm": 180, "y_mm": 240},
        coplanar_confirmed=True,
        confirmed_by_user=True,
    )
    with pytest.raises(ValueError, match="coverage"):
        hole_measurement(calibration, request)


@pytest.mark.parametrize(
    "payload",
    [b"invalid", b"", b"a" * (15 * 1024 * 1024 + 1)],
    ids=["corrupt", "empty", "oversized"],
)
def test_bad_uploads(payload):
    with pytest.raises(ValueError):
        decode_image(payload)


def test_small_image_and_exif_stripping():
    with pytest.raises(ValueError, match="small"):
        decode_image(png(np.full((200, 300, 3), 200, np.uint8)))
    image = Image.new("RGB", (1600, 1000), "gray")
    stream = BytesIO()
    exif = Image.Exif()
    exif[270] = "private fixture description"
    image.save(stream, format="JPEG", exif=exif)
    clean = decode_image(stream.getvalue())
    assert b"private fixture" not in png(clean)


@pytest.mark.parametrize("width,thickness", [(14, 7), (8, 8), (20, 3), (5, 12)])
def test_perimeter_roundtrip(width, thickness):
    assert solve_thickness(
        width, ellipse_perimeter(width, thickness), "ellipse"
    ) == pytest.approx(thickness, abs=1e-6)
    radius = min(width, thickness) / 4
    perimeter = 2 * (width + thickness) - (8 - 2 * math.pi) * radius
    assert solve_thickness(
        width, perimeter, "rounded_rectangle", radius
    ) == pytest.approx(thickness)


def test_impossible_perimeter():
    with pytest.raises(ValueError):
        solve_thickness(14, 10, "ellipse")
    with pytest.raises(ValueError):
        solve_thickness(14, 50, "rounded_rectangle", 8)


def test_fusion_conflicts_and_repeated_readings():
    workspace = Workspace(mode="manual")
    add_observation(workspace, obs(14))
    add_observation(workspace, obs(14.2, evidence="b"))
    assert len(workspace.observations) == 1
    assert workspace.measurements["handle_width"].status == "estimated"
    add_observation(workspace, obs(14.1, "manual_caliper", 0.1, evidence="c"))
    assert workspace.measurements["handle_width"].status == "cross_checked"
    assert 14.1 < workspace.measurements["handle_width"].value_mm < 14.2
    add_observation(workspace, obs(20, "manual_caliper", 0.1, evidence="d"))
    assert workspace.measurements["handle_width"].status == "conflict"
    assert workspace.measurements["handle_width"].value_mm is None


def test_correlated_evidence_not_pooled():
    workspace = Workspace(mode="photo")
    add_observation(workspace, obs(14, "photo_on_sheet", 0.5, evidence="shared"))
    add_observation(workspace, obs(14, "manual_ruler", 0.5, evidence="shared"))
    measurement = workspace.measurements["handle_width"]
    assert measurement.status == "estimated"
    assert measurement.sigma_mm == 0.5


def test_perimeter_uncertainty_and_invalidation():
    workspace = Workspace(mode="manual")
    add_observation(workspace, obs(14))
    request = PerimeterRequest(
        expected_revision=0,
        perimeter_mm=ellipse_perimeter(14, 7),
        shape="ellipse",
        confirmed_by_user=True,
    )
    thickness = perimeter_observation(workspace, request)
    assert thickness.value_mm == pytest.approx(7)
    assert thickness.sigma_mm >= 0.5
    add_observation(workspace, thickness)
    assert workspace.measurements["handle_thickness"].status == "estimated"
    add_observation(workspace, obs(14.5, evidence="changed"))
    assert "handle_thickness" not in workspace.measurements


def test_handle_width_and_parallax(calibrated):
    calibration, image = calibrated
    image = image.copy()
    cv2.rectangle(image, (930, 700), (1069, 1699), (30, 30, 30), -1)
    request = RegionRequest(
        expected_revision=0,
        calibration_id=calibration.id,
        start={"x_mm": 100, "y_mm": 75},
        end={"x_mm": 100, "y_mm": 165},
        half_width_mm=15,
        confirmed_by_user=True,
        object_height_bound_mm=5,
        camera_distance_lower_bound_mm=400,
    )
    width, length, profile, preview = region_measurements(image, calibration, request)
    assert width.value_mm == pytest.approx(14, abs=0.2)
    assert length.value_mm == pytest.approx(90)
    assert width.sigma_mm >= 0.3
    assert preview.ndim == 3
    higher = request.model_copy(update={"object_height_bound_mm": 20})
    assert region_measurements(image, calibration, higher)[0].sigma_mm > width.sigma_mm
    blank = render_sheet()
    with pytest.raises(ValueError):
        region_measurements(blank, calibration, request)
    narrow = request.model_copy(update={"half_width_mm": 4})
    with pytest.raises(ValueError):
        region_measurements(image, calibration, narrow)


def test_hole_spacing_is_not_snapped(calibrated):
    calibration, _ = calibrated
    request = HoleRequest(
        expected_revision=0,
        calibration_id=calibration.id,
        first={"x_mm": 55, "y_mm": 100},
        second={"x_mm": 150.6, "y_mm": 100},
        coplanar_confirmed=True,
        confirmed_by_user=True,
    )
    observation = hole_measurement(calibration, request)
    assert observation.value_mm == pytest.approx(95.6)
    assert observation.sigma_mm > 0.5


def create_session(client, track="adapt", mode="manual"):
    session = client.post(
        "/api/sessions", json={"track": track, "consent": True}
    ).json()
    sid = session["id"]
    response = client.post(
        f"/api/sessions/{sid}/measurement/start",
        json={"expected_revision": 0, "mode": mode},
    )
    assert response.status_code == 200, response.text
    return sid, response.json()


def test_manual_api_conflict_recovery_and_restart(tmp_path):
    app = create_app(tmp_path / "db.sqlite3")
    with TestClient(app) as client:
        sid, initial = create_session(client)
        url = f"/api/sessions/{sid}/measurements/manual"
        body = dict(
            expected_revision=1,
            dimension="handle_width",
            value_mm=14,
            instrument="manual_ruler",
            resolution_mm=1,
            confirmed_by_user=True,
        )
        first = client.post(url, json=body)
        assert first.status_code == 200, first.text
        assert client.post(url, json=body).status_code == 409
        body.update(
            expected_revision=2,
            instrument="manual_caliper",
            value_mm=20,
            resolution_mm=0.01,
        )
        conflict = client.post(url, json=body).json()
        assert (
            conflict["workspace"]["measurements"]["handle_width"]["status"]
            == "conflict"
        )
        body.update(expected_revision=3, value_mm=14.1)
        repaired = client.post(url, json=body).json()
        assert (
            repaired["workspace"]["measurements"]["handle_width"]["status"]
            == "cross_checked"
        )
        assert repaired["physical_fit_verified"] is False
        body.update(expected_revision=4, dimension="hole_spacing")
        assert client.post(url, json=body).status_code == 422
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        persisted = client.get(f"/api/sessions/{sid}/measurements").json()
        assert persisted == repaired


def test_photo_api_and_recalibration_invalidates(tmp_path):
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        sid, _ = create_session(client, mode="photo")
        image = render_sheet()
        cv2.rectangle(image, (930, 700), (1069, 1699), (30, 30, 30), -1)
        upload = png(image)
        url = f"/api/sessions/{sid}"
        bad = client.post(
            url + "/calibrate",
            files={"image": ("sheet.png", upload, "image/png")},
            data={"expected_revision": 1, "scale_check_passed": "false"},
        )
        assert bad.status_code == 422
        response = client.post(
            url + "/calibrate",
            files={"image": ("sheet.png", upload, "image/png")},
            data={"expected_revision": 1, "scale_check_passed": "true"},
        )
        assert response.status_code == 200, response.text
        calibration = response.json()["workspace"]["calibration"]
        region = dict(
            expected_revision=2,
            calibration_id=calibration["id"],
            start={"x_mm": 100, "y_mm": 75},
            end={"x_mm": 100, "y_mm": 165},
            half_width_mm=15,
            confirmed_by_user=True,
            object_height_bound_mm=5,
            camera_distance_lower_bound_mm=400,
        )
        measured = client.post(url + "/region", json=region)
        assert measured.status_code == 200, measured.text
        assert client.get(url + "/measurement-images/region-preview").status_code == 200
        next_cal = client.post(
            url + "/calibrate",
            files={"image": ("sheet.png", upload, "image/png")},
            data={"expected_revision": 3, "scale_check_passed": "true"},
        )
        assert next_cal.status_code == 200, next_cal.text
        assert not next_cal.json()["workspace"]["measurements"]
        assert client.get(url + "/measurement-images/region-preview").status_code == 404
        region["expected_revision"] = 4
        assert client.post(url + "/region", json=region).status_code == 409


def test_repair_and_pdf_api(tmp_path):
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        sid, _ = create_session(client, track="repair")
        response = client.post(
            f"/api/sessions/{sid}/measurements/manual",
            json=dict(
                expected_revision=1,
                dimension="hole_spacing",
                value_mm=96,
                instrument="manual_ruler",
                resolution_mm=1,
                confirmed_by_user=True,
            ),
        )
        assert response.status_code == 200
        assert response.json()["missing_dimensions"] == ["hole_diameter"]
        response = client.get("/api/fit-sheet.pdf")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")
        assert response.headers["content-type"] == "application/pdf"


def test_actual_pdf_renders_at_metric_scale():
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(fit_sheet_pdf()) as pdf:
        page = pdf[0]
        assert page.get_width() == pytest.approx(210 * MM_TO_PT, abs=0.01)
        assert page.get_height() == pytest.approx(297 * MM_TO_PT, abs=0.01)
        bitmap = page.render(scale=10 / MM_TO_PT).to_pil().convert("RGB")
        image = cv2.cvtColor(np.array(bitmap), cv2.COLOR_RGB2BGR)
        calibration, _ = calibrate(image, scale_check_passed=True)
        assert calibration.marker_ids == [0, 1, 2, 3]
        assert calibration.reprojection_rms_mm < 0.15
        # The PDF gray region must agree with the calibration layout.
        assert np.mean(image[800:900, 800:900]) == pytest.approx(166, abs=1)


def test_evaluation_uses_supplied_truth_only():
    from tools.evaluate_measurements import evaluate

    rows = [
        dict(
            object_id="synthetic_test_only",
            method="fixture",
            dimension="width",
            estimate_mm=v,
            reference_mm=14,
        )
        for v in [13, 14, 15]
    ]
    result = evaluate(rows)["results"][0]
    assert result["mean_absolute_error_mm"] == pytest.approx(2 / 3)
    assert result["bias_mm"] == 0
    assert result["mean_within_object_sd_mm"] == 1
    with pytest.raises(ValueError, match="No measurements"):
        evaluate([])
    with pytest.raises(ValueError):
        evaluate([dict(rows[0], estimate_mm=float("nan"))])


def test_full_manual_and_perimeter_api(tmp_path):
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        sid, _ = create_session(client)
        root = f"/api/sessions/{sid}"
        for revision, dimension, value in [
            (1, "handle_width", 14),
            (2, "covered_length", 100),
        ]:
            response = client.post(
                root + "/measurements/manual",
                json=dict(
                    expected_revision=revision,
                    dimension=dimension,
                    value_mm=value,
                    instrument="manual_ruler",
                    resolution_mm=0.5,
                    confirmed_by_user=True,
                ),
            )
            assert response.status_code == 200
        response = client.post(
            root + "/measurements/perimeter",
            json=dict(
                expected_revision=3,
                perimeter_mm=ellipse_perimeter(14, 7),
                shape="ellipse",
                confirmed_by_user=True,
            ),
        )
        assert response.status_code == 200, response.text
        assert response.json()["dimensionally_complete"] is True
        assert response.json()["physical_fit_verified"] is False
        response = client.post(
            root + "/measurements/manual",
            json=dict(
                expected_revision=4,
                dimension="handle_width",
                value_mm=14.2,
                instrument="manual_ruler",
                resolution_mm=0.5,
                confirmed_by_user=True,
            ),
        )
        assert response.status_code == 200
        assert response.json()["missing_dimensions"] == ["handle_thickness"]
