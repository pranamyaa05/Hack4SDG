import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.contracts import Session, State
from backend.storage import RevisionConflict

from .engine import build_spec, recommendations
from .models import FeedbackRequest, GenerateRequest, ManufacturingSpec, RefitRequest
from .package import build_package

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def context(request, sid, revision=None):
    try:
        session, workspace = request.app.state.measurements.load(str(sid))
        _, analysis = request.app.state.analysis.load(str(sid))
    except KeyError:
        raise HTTPException(404, "Session not found")
    if revision is not None and session.revision != revision:
        raise HTTPException(409, "Session changed; reload and retry")
    if workspace is None:
        raise HTTPException(409, "Start and complete measurement first")
    if session.state not in {State.MEASURING, State.READY}:
        raise HTTPException(409, "Session is not ready for design")
    return session, workspace, analysis


@router.get("/sessions/{session_id}/recommendations")
def propose(session_id: UUID, request: Request):
    session, workspace, analysis = context(request, session_id)
    try:
        options = recommendations(session, analysis, workspace)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {
        "revision": session.revision,
        "options": options,
        "physical_fit_verified": False,
    }


@router.post("/sessions/{session_id}/generate", status_code=201)
def generate(session_id: UUID, body: GenerateRequest, request: Request):
    session, workspace, analysis = context(request, session_id, body.expected_revision)
    if session.state == State.READY:
        raise HTTPException(
            409, "This session already has a design. Use Re-fit to create a revision."
        )
    with request.app.state.sessions.connect() as db:
        link = db.execute(
            "SELECT parent_design_id FROM refit_links WHERE session_id=?", (session.id,)
        ).fetchone()
    parent = link[0] if link else None
    if body.parent_design_id is not None and body.parent_design_id != parent:
        raise HTTPException(422, "Parent design must come from the Re-fit endpoint")
    body = body.model_copy(update={"parent_design_id": parent})
    try:
        spec = build_spec(session, analysis, workspace, body)
        rectified = request.app.state.measurements.image(session.id, "rectified")
        selection = workspace.selections.get(
            "handle_region" if session.track.value == "adapt" else "hole_centres"
        )
        if not selection:
            rectified = None
        record = build_package(
            spec, request.app.state.output_root, rectified, selection
        )
    except ImportError:
        raise HTTPException(
            503, "Geometry dependencies are unavailable. Install the project cad extra."
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        # Native CAD exceptions must not expose local paths or leave an apparently valid design.
        logger.exception("Geometry/output generation failed for session %s", session.id)
        raise HTTPException(
            422,
            "CAD or output validation failed. Check the measurements and try another supported size.",
        )
    record["session_id"] = session.id
    try:
        updated = request.app.state.designs.publish(session, spec, record)
    except RevisionConflict as exc:
        raise HTTPException(409, str(exc))
    return {"revision": updated.revision, "design": record}


def get_record(request, did):
    record = request.app.state.designs.get(str(did))
    if record is None:
        raise HTTPException(404, "Design not found")
    return record


@router.get("/designs")
def list_designs(request: Request):
    return {"designs": request.app.state.designs.list()}


@router.get("/designs/{design_id}")
def design(design_id: UUID, request: Request):
    return get_record(request, design_id)


@router.get("/designs/{design_id}/files/{filename}")
def file(design_id: UUID, filename: str, request: Request):
    record = get_record(request, design_id)
    if filename not in record["files"] or Path(filename).name != filename:
        raise HTTPException(404, "File not found")
    path = request.app.state.output_root / str(design_id) / filename
    if not path.is_file():
        raise HTTPException(404, "Artifact is missing")
    return FileResponse(
        path,
        filename=filename,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.get("/designs/{design_id}/package.zip")
def package(design_id: UUID, request: Request):
    return file(design_id, "package.zip", request)


@router.post("/designs/{design_id}/feedback")
def feedback(design_id: UUID, body: FeedbackRequest, request: Request):
    get_record(request, design_id)
    if body.kept_in_use and body.outcome != "fits":
        raise HTTPException(
            422, "Confirm a successful fit before recording an item kept in use"
        )
    request.app.state.designs.feedback(str(design_id), body.model_dump())
    return {
        "recorded": True,
        "note": "User-reported feedback; the original design specification remains unchanged.",
    }


@router.post("/designs/{design_id}/refit", status_code=201)
def refit(design_id: UUID, body: RefitRequest, request: Request):
    record = get_record(request, design_id)
    original, analysis = request.app.state.analysis.load(record["session_id"])
    session = request.app.state.sessions.create(
        Session(track=original.track, language=original.language, consent=True)
    )
    images = {}
    for name in ("original", "ai"):
        data = request.app.state.analysis.image(original.id, name)
        if data:
            images[name] = data
    updated = request.app.state.analysis.save(
        session, analysis, 0, state=State.CALIBRATING, images=images
    )
    with request.app.state.sessions.connect() as db:
        db.execute("INSERT INTO refit_links VALUES (?,?)", (session.id, str(design_id)))
    return {
        "session": updated,
        "parent_design_id": str(design_id),
        "previous_measurements": record["spec"]["measurements"],
        "message": "New design session. Confirm updated measurements before generating; the original design is preserved.",
    }


@router.get("/statistics")
def statistics(request: Request):
    records = request.app.state.designs.list()
    with request.app.state.sessions.connect() as db:
        sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    feedback = [r["feedback"] for r in records if r["feedback"]]
    tried = [f for f in feedback if f["outcome"] != "not_tested"]
    kept = {
        r["session_id"]
        for r in records
        if r["feedback"] and r["feedback"]["kept_in_use"]
    }
    # Count a Re-fit chain once when reporting objects kept in use.
    by_id = {r["id"]: r for r in records}
    roots = set()
    for r in records:
        if r["session_id"] not in kept:
            continue
        root = r
        seen = set()
        while root["spec"].get("parent_design_id") in by_id and root["id"] not in seen:
            seen.add(root["id"])
            root = by_id[root["spec"]["parent_design_id"]]
        roots.add(root["id"])
    return {
        "sessions_started": sessions,
        "designs_generated": len(records),
        "adapt_designs": sum(r["spec"]["track"] == "adapt" for r in records),
        "repair_designs": sum(r["spec"]["track"] == "repair" for r in records),
        "reported_fit_trials": len(tried),
        "reported_fits": sum(f["outcome"] == "fits" for f in tried),
        "reported_items_kept_in_use": len(roots),
        "solid_material_estimate_g": sum(
            r["ledger"]["solid_material_estimate_g"] for r in records
        ),
        "limitations": [
            "Fit and continued use are user-reported, not independently verified.",
            "Generated designs are not successful repairs. Material totals are estimates for all generated designs, not actual filament consumed.",
            "Re-fit chains are deduplicated for reported items kept in use. No CO2 or cost-saving claim is computed.",
        ],
    }


@router.get("/contracts/manufacturing-spec")
def schema():
    return ManufacturingSpec.model_json_schema()
