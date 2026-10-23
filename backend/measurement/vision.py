from __future__ import annotations

import warnings
from io import BytesIO
from math import hypot

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .fit_sheet import MARKERS, PPM, WORK_AREA, dictionary, marker_corners
from .models import Calibration, HoleRequest, Observation, RegionRequest

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 20_000_000


def decode_image(data: bytes) -> np.ndarray:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Upload a JPEG or PNG no larger than 15 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG"}:
                    raise ValueError("Only JPEG and PNG are supported")
                if original.width * original.height > MAX_PIXELS:
                    raise ValueError(
                        "Image exceeds 20 megapixels; resize before upload"
                    )
                image = np.asarray(ImageOps.exif_transpose(original).convert("RGB"))
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Image cannot be decoded; upload a valid JPEG or PNG") from exc
    if min(image.shape[:2]) < 600 or max(image.shape[:2]) < 1600:
        raise ValueError(
            "Photo is too small; use at least 1600 pixels on the long edge and 600 on the short edge"
        )
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def project(points, homography):
    return cv2.perspectiveTransform(
        np.asarray(points, dtype=np.float64).reshape(-1, 1, 2), homography
    ).reshape(-1, 2)


def calibrate(
    image: np.ndarray, *, scale_check_passed: bool
) -> tuple[Calibration, np.ndarray]:
    if not scale_check_passed:
        raise ValueError(
            "Confirm the printed scale-check box against a card or ruler before calibrating"
        )
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary(), parameters)
    corners, ids, _ = detector.detectMarkers(gray)
    matches = {}
    if ids is not None:
        for box, marker_id in zip(corners, ids.flatten()):
            if int(marker_id) not in MARKERS:
                continue
            if int(marker_id) in matches:
                raise ValueError(
                    "Duplicate Fit Sheet markers; photograph only one flat sheet"
                )
            matches[int(marker_id)] = box.reshape(4, 2).astype(np.float64)
    if len(matches) < 3:
        raise ValueError(
            "At least three Fit Sheet markers must be visible; retake or use manual measurements"
        )
    order = sorted(matches)
    src = np.concatenate([matches[i] for i in order])
    dst = np.concatenate([marker_corners(i) for i in order])
    if min(np.linalg.norm(v[1] - v[0]) for v in matches.values()) < 60:
        raise ValueError(
            "Markers are too small in the photo; move closer while keeping the full sheet visible"
        )
    h, _ = cv2.findHomography(src, dst, method=0)
    if h is None or not np.isfinite(h).all() or abs(np.linalg.det(h)) < 1e-14:
        raise ValueError("Calibration is degenerate; flatten the sheet and retake")
    residual = np.linalg.norm(project(src, h) - dst, axis=1)
    rms = float(np.sqrt(np.mean(residual**2)))
    holdout = []
    for excluded in order:
        training = [i for i in order if i != excluded]
        hs, _ = cv2.findHomography(
            np.concatenate([matches[i] for i in training]),
            np.concatenate([marker_corners(i) for i in training]),
            method=0,
        )
        if hs is None:
            raise ValueError(
                "Cannot independently check marker geometry; retake the photo"
            )
        holdout.extend(
            np.linalg.norm(
                project(matches[excluded], hs) - marker_corners(excluded), axis=1
            )
        )
    cv_rms = float(np.sqrt(np.mean(np.square(holdout))))
    if rms > 1 or cv_rms > 1.5 or float(np.max(residual)) > 2:
        raise ValueError(
            "Markers disagree with a flat sheet; flatten it, improve lighting, and retake"
        )
    scale = np.diag([PPM, PPM, 1.0])
    rectified = cv2.warpPerspective(
        image,
        scale @ h,
        (2100, 2970),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    x0, y0, x1, y1 = WORK_AREA
    work = cv2.cvtColor(
        rectified[y0 * PPM : y1 * PPM, x0 * PPM : x1 * PPM], cv2.COLOR_BGR2GRAY
    )
    if float(work.mean()) < 35 or float(work.mean()) > 240:
        raise ValueError(
            "Work area is too dark or overexposed; retake in diffuse light"
        )
    notes = [
        "Reprojection residuals measure marker agreement, not real-world object accuracy.",
        "Lens distortion and object height are not corrected by a planar homography.",
    ]
    if len(matches) == 3:
        notes.append(
            "Only three markers found; measure inside the detected marker triangle."
        )
    hull = cv2.convexHull(dst.astype(np.float32)).reshape(-1, 2)
    calibration = Calibration(
        marker_ids=order,
        homography=h.tolist(),
        reprojection_rms_mm=rms,
        leave_one_marker_out_rms_mm=cv_rms,
        quality="good" if rms <= 0.5 and cv_rms <= 0.75 else "acceptable",
        image_width=image.shape[1],
        image_height=image.shape[0],
        coverage_mm=hull.tolist(),
        warnings=notes,
    )
    return calibration, rectified


def check_coverage(points, calibration: Calibration):
    hull = np.asarray(calibration.coverage_mm, dtype=np.float32)
    for point in points:
        x, y = map(float, point)
        if (
            not (0 <= x < 210 and 0 <= y < 297)
            or cv2.pointPolygonTest(hull, (x, y), False) < 0
        ):
            raise ValueError(
                "Selection lies outside calibrated marker coverage; retake with all four markers or move selection"
            )


def region_measurements(
    rectified: np.ndarray, calibration: Calibration, request: RegionRequest
):
    start = np.array([request.start.x_mm, request.start.y_mm])
    end = np.array([request.end.x_mm, request.end.y_mm])
    length = float(np.linalg.norm(end - start))
    if length < 10 or length > 150:
        raise ValueError("Select a handle segment between 10 and 150 mm long")
    axis = (end - start) / length
    normal = np.array([-axis[1], axis[0]])
    half = request.half_width_mm
    box = np.array(
        [
            start - normal * half,
            start + normal * half,
            end - normal * half,
            end + normal * half,
        ]
    )
    check_coverage(box, calibration)
    x0, y0, x1, y1 = WORK_AREA
    if np.any(box < [x0, y0]) or np.any(box > [x1, y1]):
        raise ValueError("Handle selection must stay within the clear gray work area")
    n, m = round(length * PPM), round(2 * half * PPM) + 1
    along = np.linspace(0, length, n)
    across = np.linspace(-half, half, m)
    coords = (
        start[None, None, :]
        + along[None, :, None] * axis
        + across[:, None, None] * normal
    )
    patch = cv2.remap(
        rectified,
        (coords[:, :, 0] * PPM).astype(np.float32),
        (coords[:, :, 1] * PPM).astype(np.float32),
        cv2.INTER_LINEAR,
    )
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < 10:
        raise ValueError(
            "Handle region is blurred or lacks contrast; retake or use manual measurements"
        )
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).astype(np.float32)
    flank = max(3, round(0.1 * m))
    background = np.median(
        np.concatenate([lab[:flank].reshape(-1, 3), lab[-flank:].reshape(-1, 3)]),
        axis=0,
    )
    delta = np.linalg.norm(lab - background, axis=2)
    # Otsu separates color distance; minimum contrast prevents quantizing sensor noise as an object.
    otsu, _ = cv2.threshold(
        np.clip(delta, 0, 255).astype(np.uint8),
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    mask = (delta > max(12, float(otsu))).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count < 2:
        raise ValueError(
            "Could not separate the handle from the sheet; adjust the bracket or measure manually"
        )
    label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = labels == label
    if mask[:2].any() or mask[-2:].any():
        raise ValueError("Handle touches the bracket sides; widen the selection")
    widths = []
    for column in range(n):
        occupied = np.flatnonzero(mask[:, column])
        if len(occupied) >= 3:
            # A disconnected reflection/shadow is not allowed to bridge a large gap.
            if occupied[-1] - occupied[0] + 1 > len(occupied) * 1.15:
                continue
            widths.append((occupied[-1] - occupied[0] + 1) / PPM)
    if len(widths) < 0.9 * n:
        raise ValueError(
            "Handle outline is incomplete; adjust the region, retake, or enter width manually"
        )
    width = float(np.percentile(widths, 95))
    if width < 2 or width > 60:
        raise ValueError(
            "Detected width is outside the supported handle range; confirm manually"
        )
    spread = float(np.subtract(*np.percentile(widths, [75, 25])) / 1.349)
    # User-supplied bounds are explicitly conservative; they are not camera pose estimates.
    height = request.object_height_bound_mm
    distance = request.camera_distance_lower_bound_mm
    parallax = width * height / (distance - height)
    calibration_floor = max(
        0.3, calibration.reprojection_rms_mm, calibration.leave_one_marker_out_rms_mm
    )
    sigma = hypot(calibration_floor, hypot(0.2, hypot(spread, parallax)))
    evidence = [calibration.id]
    notes = [
        "95th-percentile visible width over the confirmed bracket; inspect the profile before fabrication.",
        f"User-declared object-height bound {height} mm and camera-distance lower bound {distance} mm.",
        "Parallax is included as an uncertainty allowance; lens distortion is uncalibrated.",
    ]
    width_obs = Observation(
        dimension="handle_width",
        value_mm=width,
        sigma_mm=sigma,
        method="photo_on_sheet",
        evidence_ids=evidence,
        confirmed_by_user=True,
        notes=notes,
    )
    length_obs = Observation(
        dimension="covered_length",
        value_mm=length,
        sigma_mm=hypot(calibration_floor, length * height / (distance - height)),
        method="photo_on_sheet",
        evidence_ids=evidence,
        confirmed_by_user=True,
        notes=["Covered length is set by user-selected endpoints."],
    )
    profile = {
        "width_mm": widths[:: max(1, len(widths) // 150)],
        "minimum_mm": min(widths),
        "maximum_mm": max(widths),
    }
    # Mask preview makes segmentation errors reviewable by the future UI.
    preview = patch.copy()
    preview[mask] = (preview[mask] * 0.5 + np.array([40, 190, 60]) * 0.5).astype(
        np.uint8
    )
    return width_obs, length_obs, profile, preview


def hole_measurement(calibration: Calibration, request: HoleRequest):
    a = [request.first.x_mm, request.first.y_mm]
    b = [request.second.x_mm, request.second.y_mm]
    check_coverage([a, b], calibration)
    spacing = hypot(a[0] - b[0], a[1] - b[1])
    if spacing < 10 or spacing > 300:
        raise ValueError("Supported hole spacing is 10 to 300 mm")
    floor = max(
        0.3, calibration.reprojection_rms_mm, calibration.leave_one_marker_out_rms_mm
    )
    sigma = hypot(2**0.5 * request.click_uncertainty_mm, floor)
    return Observation(
        dimension="hole_spacing",
        value_mm=spacing,
        sigma_mm=sigma,
        method="photo_on_sheet",
        evidence_ids=[calibration.id],
        confirmed_by_user=True,
        notes=[
            "User-selected centres on a confirmed coplanar surface; raw distance is not snapped to a standard.",
            "Mounting-hole diameter and screw details still require separate measurement.",
        ],
    )
