from typing import Annotated
from uuid import UUID, uuid4

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.contracts import State, Track
from backend.storage import RevisionConflict

from .fit_sheet import fit_sheet_pdf
from .metrology import add_observation, perimeter_observation, rebuild
from .models import (
    HoleRequest,
    ManualRequest,
    Observation,
    PerimeterRequest,
    RegionRequest,
    StartRequest,
    Workspace,
)
from .vision import (
    MAX_BYTES,
    calibrate,
    decode_image,
    hole_measurement,
    region_measurements,
)

router = APIRouter(prefix="/api")
EDITABLE = {State.CALIBRATING, State.MEASURING}
DIMENSIONS = {
    Track.ADAPT: {"handle_width", "handle_thickness", "covered_length"},
    Track.REPAIR: {"hole_spacing", "hole_diameter"},
}


def load(request, session_id, expected_revision=None):
    try:
        session, workspace = request.app.state.measurements.load(str(session_id))
    except KeyError:
        raise HTTPException(404, "Session not found")
    if expected_revision is not None and session.revision != expected_revision:
        raise HTTPException(409, "Session changed; reload and retry")
    return session, workspace


def editable(request, session_id, revision):
    session, workspace = load(request, session_id, revision)
    if workspace is None or session.state not in EDITABLE:
        raise HTTPException(409, "Start a measurement workspace before adding evidence")
    return session, workspace


def save(request, session, workspace, revision, **kwargs):
    try:
        updated = request.app.state.measurements.save(
            session, workspace, revision, **kwargs
        )
    except RevisionConflict as exc:
        raise HTTPException(409, str(exc))
    return result(updated, workspace)


def result(session, workspace):
    missing = [
        key
        for key in sorted(DIMENSIONS[session.track])
        if key not in workspace.measurements
        or workspace.measurements[key].status in {"unknown", "conflict"}
    ]
    return {
        "session_id": session.id,
        "revision": session.revision,
        "state": session.state,
        "workspace": workspace,
        "missing_dimensions": missing,
        "dimensionally_complete": not missing,
        "physical_fit_verified": False,
    }


def dimension_allowed(session, dimension):
    if dimension not in DIMENSIONS[session.track]:
        raise HTTPException(422, "Dimension is not applicable to this track")


def encode_png(image):
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Image encoding failed")
    return encoded.tobytes()


@router.get("/fit-sheet.pdf")
def sheet():
    return Response(
        fit_sheet_pdf(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="refit-fit-sheet-v1.pdf"'},
    )


@router.post("/sessions/{session_id}/measurement/start")
def start(session_id: UUID, body: StartRequest, request: Request):
    session, existing = load(request, session_id, body.expected_revision)
    if session.state not in {
        State.CREATED,
        State.CALIBRATING,
        State.MEASURING,
        State.NEEDS_INFO,
    }:
        raise HTTPException(409, "Session is not ready to start measurement")
    if existing is not None:
        raise HTTPException(
            409, "Measurement already started; continue the existing workspace"
        )
    from backend.ai.questions import support_decision

    _, analysis = request.app.state.analysis.load(session.id)
    if (
        analysis.image is not None or analysis.confirmation is not None
    ) and support_decision(session.track, analysis)["status"] != "supported":
        raise HTTPException(
            409, "Complete object confirmation and required questions first"
        )
    workspace = Workspace(mode=body.mode)
    return save(
        request,
        session,
        workspace,
        body.expected_revision,
        state=State.MEASURING if body.mode == "manual" else State.CALIBRATING,
    )


@router.get("/sessions/{session_id}/measurements")
def measurements(session_id: UUID, request: Request):
    session, workspace = load(request, session_id)
    if workspace is None:
        raise HTTPException(409, "Measurement has not started")
    return result(session, workspace)


@router.post("/sessions/{session_id}/measurements/manual")
def manual(session_id: UUID, body: ManualRequest, request: Request):
    session, workspace = editable(request, session_id, body.expected_revision)
    dimension_allowed(session, body.dimension)
    floor = 0.5 if body.instrument == "manual_ruler" else 0.05
    sigma = max(body.resolution_mm, body.uncertainty_mm or 0, floor)
    observation = Observation(
        dimension=body.dimension,
        value_mm=body.value_mm,
        sigma_mm=sigma,
        method=body.instrument,
        evidence_ids=[str(uuid4())],
        confirmed_by_user=True,
        notes=[
            "User-confirmed manual reading. Instrument resolution is not an accuracy certificate.",
            "Uncertainty floor is provisional; this reading alone does not prove physical fit.",
        ],
    )
    add_observation(workspace, observation)
    return save(
        request, session, workspace, body.expected_revision, state=State.MEASURING
    )


@router.post("/sessions/{session_id}/calibrate")
def calibration(
    session_id: UUID,
    request: Request,
    image: Annotated[UploadFile, File()],
    expected_revision: Annotated[int, Form(ge=0)],
    scale_check_passed: Annotated[bool, Form()],
):
    session, workspace = editable(request, session_id, expected_revision)
    data = image.file.read(MAX_BYTES + 1)
    try:
        decoded = decode_image(data)
        calibration, rectified = calibrate(
            decoded, scale_check_passed=scale_check_passed
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    workspace.mode = "photo"
    workspace.calibration = calibration
    workspace.selections = {}
    # A new photo invalidates the old photo observations and dependent perimeter inference.
    workspace.observations = [
        o
        for o in workspace.observations
        if o.method not in {"photo_on_sheet", "paper_strip"}
    ]
    rebuild(workspace)
    return save(
        request,
        session,
        workspace,
        expected_revision,
        state=State.MEASURING,
        clear_images=True,
        images={"rectified": encode_png(rectified)},
    )


def current_calibration(workspace, calibration_id):
    if workspace.calibration is None or workspace.calibration.id != calibration_id:
        raise HTTPException(
            409, "Calibration changed or is missing; reload before selecting a region"
        )
    return workspace.calibration


@router.post("/sessions/{session_id}/region")
def region(session_id: UUID, body: RegionRequest, request: Request):
    session, workspace = editable(request, session_id, body.expected_revision)
    if session.track != Track.ADAPT:
        raise HTTPException(422, "Handle-region measurement applies to Adapt only")
    calibration = current_calibration(workspace, body.calibration_id)
    data = request.app.state.measurements.image(session.id, "rectified")
    if data is None:
        raise HTTPException(409, "Rectified image is missing; recalibrate")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    try:
        width, length, profile, preview = region_measurements(image, calibration, body)
        add_observation(workspace, width)
        add_observation(workspace, length)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    workspace.selections["handle_region"] = {
        "request": body.model_dump(exclude={"expected_revision"}),
        "profile": profile,
    }
    response = save(
        request,
        session,
        workspace,
        body.expected_revision,
        images={"region-preview": encode_png(preview)},
    )
    response["profile"] = profile
    return response


@router.post("/sessions/{session_id}/hole-spacing")
def holes(session_id: UUID, body: HoleRequest, request: Request):
    session, workspace = editable(request, session_id, body.expected_revision)
    if session.track != Track.REPAIR:
        raise HTTPException(422, "Hole spacing applies to Repair only")
    calibration = current_calibration(workspace, body.calibration_id)
    try:
        add_observation(workspace, hole_measurement(calibration, body))
        workspace.selections["hole_centres"] = body.model_dump(
            exclude={"expected_revision"}
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return save(request, session, workspace, body.expected_revision)


@router.post("/sessions/{session_id}/measurements/perimeter")
def perimeter(session_id: UUID, body: PerimeterRequest, request: Request):
    session, workspace = editable(request, session_id, body.expected_revision)
    if session.track != Track.ADAPT:
        raise HTTPException(422, "Paper-strip thickness applies to Adapt only")
    try:
        add_observation(workspace, perimeter_observation(workspace, body))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return save(
        request, session, workspace, body.expected_revision, state=State.MEASURING
    )


@router.get("/sessions/{session_id}/measurement-images/{name}")
def measurement_image(session_id: UUID, name: str, request: Request):
    load(request, session_id)
    if name not in {"rectified", "region-preview"}:
        raise HTTPException(404, "Image not found")
    data = request.app.state.measurements.image(str(session_id), name)
    if data is None:
        raise HTTPException(404, "Image not found")
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})
