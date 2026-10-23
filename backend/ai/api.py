from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.contracts import State, Track
from backend.measurement.vision import MAX_BYTES
from backend.storage import RevisionConflict

from .intake import prepare_image
from .models import (
    AnalysisWorkspace,
    AnalyzeRequest,
    AnswerRequest,
    Answers,
    Confirmation,
    ConfirmRequest,
    RevisionBody,
)
from .questions import extract_explicit_difficulty, questions, support_decision

router = APIRouter(prefix="/api")


def load(request, sid, revision=None):
    try:
        session, workspace = request.app.state.analysis.load(str(sid))
    except KeyError:
        raise HTTPException(404, "Session not found")
    if revision is not None and revision != session.revision:
        raise HTTPException(409, "Session changed; reload and retry")
    return session, workspace


def editable(request, session):
    if request.app.state.analysis.has_measurements(session.id):
        raise HTTPException(
            409,
            "Measurement has started. Use a new session to change object identity or needs.",
        )
    if session.state not in {
        State.CREATED,
        State.CONFIRMING,
        State.CLARIFYING,
        State.CALIBRATING,
        State.NEEDS_INFO,
    }:
        raise HTTPException(409, "Analysis cannot be edited in the current state")


def result(session, workspace):
    return {
        "session_id": session.id,
        "revision": session.revision,
        "state": session.state,
        "workspace": workspace,
        "support": support_decision(session.track, workspace),
        "questions": questions(session.track, workspace),
        "object_choices": ["spoon", "fork", "knife", "other", "unknown"]
        if session.track == Track.ADAPT
        else ["drawer_handle", "other", "unknown"],
    }


def save(request, session, workspace, revision, state, **kwargs):
    try:
        updated = request.app.state.analysis.save(
            session, workspace, revision, state=state, **kwargs
        )
    except RevisionConflict as exc:
        raise HTTPException(409, str(exc))
    return updated


@router.get("/ai/providers")
def providers(request: Request):
    return request.app.state.ai_service.settings.public_status()


@router.post("/sessions/{session_id}/image")
def upload(
    session_id: UUID,
    request: Request,
    image: Annotated[UploadFile, File()],
    expected_revision: Annotated[int, Form(ge=0)],
    user_text: Annotated[str, Form(max_length=2000)] = "",
):
    session, _ = load(request, session_id, expected_revision)
    editable(request, session)
    try:
        metadata, clean, small = prepare_image(image.file.read(MAX_BYTES + 1))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    workspace = AnalysisWorkspace(image=metadata, user_text=user_text)
    inferred = (
        extract_explicit_difficulty(user_text) if session.track == Track.ADAPT else None
    )
    if inferred:
        workspace.answers.difficulty = inferred
        workspace.answer_sources["difficulty"] = "explicit_user_text_rule"
    updated = save(
        request,
        session,
        workspace,
        expected_revision,
        State.CREATED,
        images={"original": clean, "ai": small},
    )
    return result(updated, workspace)


@router.get("/sessions/{session_id}/analysis")
def analysis(session_id: UUID, request: Request):
    session, workspace = load(request, session_id)
    return result(session, workspace)


@router.post("/sessions/{session_id}/analyze")
def analyze(session_id: UUID, body: AnalyzeRequest, request: Request):
    session, workspace = load(request, session_id, body.expected_revision)
    editable(request, session)
    service = request.app.state.ai_service
    provider = body.provider or service.settings.provider
    if provider == "gemini" and not body.cloud_consent:
        raise HTTPException(
            422,
            "Cloud analysis sends the resized image and notes to Gemini. Explicit cloud consent is required.",
        )
    if provider != "manual" and workspace.image is None:
        raise HTTPException(
            422, "Upload an object image first, or choose manual confirmation"
        )
    if not service.lock.acquire(blocking=False):
        raise HTTPException(
            409,
            "Another analysis is running. Retry shortly or use manual confirmation.",
        )
    try:
        if body.user_text is not None:
            workspace.user_text = body.user_text
            explicit = (
                extract_explicit_difficulty(body.user_text)
                if session.track == Track.ADAPT
                else None
            )
            if workspace.answer_sources.get("difficulty") == "explicit_user_text_rule":
                workspace.answers.difficulty = None
                workspace.answer_sources.pop("difficulty", None)
            if explicit:
                workspace.answers.difficulty = explicit
                workspace.answer_sources["difficulty"] = "explicit_user_text_rule"
        workspace.confirmation = None
        workspace.analysis = None
        workspace.provider = provider
        workspace.model = (
            service.settings.ollama_model
            if provider == "ollama"
            else (service.settings.gemini_model if provider == "gemini" else None)
        )
        workspace.cloud_consent = provider == "gemini" and body.cloud_consent
        workspace.provider_status = "running"
        claimed = save(
            request, session, workspace, body.expected_revision, State.ANALYZING
        )
        if provider == "manual":
            workspace.provider_status = "manual"
            workspace.attempts = 0
            workspace.latency_ms = 0
            workspace.message = (
                "Choose the object and component yourself; no AI inference was run."
            )
        else:
            image = request.app.state.analysis.image(session.id, "ai")
            if image is None:
                workspace.provider_status = "unavailable"
                workspace.message = "Prepared image is missing. Re-upload or choose the object manually."
            else:
                output, status, attempts, latency = service.run(
                    provider, image, workspace.user_text, session.track.value
                )
                workspace.analysis = output
                workspace.provider_status = status
                workspace.attempts = attempts
                workspace.latency_ms = latency
                workspace.message = (
                    "Review and confirm or correct the AI interpretation."
                    if status == "ok"
                    else "AI analysis is unavailable or could not produce a valid interpretation. Choose the object manually."
                )
        updated = save(request, claimed, workspace, claimed.revision, State.CONFIRMING)
        return result(updated, workspace)
    finally:
        service.lock.release()


@router.post("/sessions/{session_id}/analysis/cancel")
def cancel(session_id: UUID, body: RevisionBody, request: Request):
    session, workspace = load(request, session_id, body.expected_revision)
    if session.state != State.ANALYZING:
        raise HTTPException(409, "No analysis is running")
    workspace.provider_status = "interrupted"
    workspace.analysis = None
    workspace.message = "Analysis interrupted. Choose the object manually or retry."
    updated = save(
        request, session, workspace, body.expected_revision, State.CONFIRMING
    )
    # A late provider result cannot overwrite this revision.
    return result(updated, workspace)


@router.post("/sessions/{session_id}/confirm-object")
def confirm(session_id: UUID, body: ConfirmRequest, request: Request):
    session, workspace = load(request, session_id, body.expected_revision)
    editable(request, session)
    workspace.confirmation = Confirmation.model_validate(
        body.model_dump(exclude={"expected_revision"})
    )
    if workspace.provider is None:
        workspace.provider = "manual"
        workspace.provider_status = "manual"
    decision = support_decision(session.track, workspace)
    state = (
        State.NEEDS_INFO
        if decision["status"] == "unsupported"
        else (
            State.CALIBRATING if decision["status"] == "supported" else State.CLARIFYING
        )
    )
    updated = save(request, session, workspace, body.expected_revision, state)
    return result(updated, workspace)


@router.post("/sessions/{session_id}/answers")
def answers(session_id: UUID, body: AnswerRequest, request: Request):
    session, workspace = load(request, session_id, body.expected_revision)
    editable(request, session)
    if workspace.confirmation is None:
        raise HTTPException(409, "Confirm the object first")
    updates = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    permitted = (
        {"difficulty", "material_preference", "hand_preference"}
        if session.track == Track.ADAPT
        else {"repair_case", "surface_condition"}
    )
    if set(updates) - permitted:
        raise HTTPException(422, "Answer is not applicable to this track")
    workspace.answers = Answers.model_validate(
        {**workspace.answers.model_dump(), **updates}
    )
    workspace.answer_sources.update({key: "user_answer" for key in updates})
    decision = support_decision(session.track, workspace)
    state = (
        State.NEEDS_INFO
        if decision["status"] == "unsupported"
        else (
            State.CALIBRATING if decision["status"] == "supported" else State.CLARIFYING
        )
    )
    updated = save(request, session, workspace, body.expected_revision, state)
    return result(updated, workspace)


@router.get("/sessions/{session_id}/image")
def image(session_id: UUID, request: Request):
    load(request, session_id)
    data = request.app.state.analysis.image(str(session_id), "original")
    if data is None:
        raise HTTPException(404, "No image uploaded")
    return Response(
        data, media_type="image/jpeg", headers={"Cache-Control": "no-store"}
    )
