"""Internal transitions. Stage services must check their exit conditions first."""

from .contracts import Session, State, utcnow

PATH = [
    State.CREATED,
    State.ANALYZING,
    State.CONFIRMING,
    State.CLARIFYING,
    State.CALIBRATING,
    State.MEASURING,
    State.RECOMMENDING,
    State.SELECTED,
    State.GENERATING,
    State.READY,
]
NEXT = dict(zip(PATH, PATH[1:]))


def transition(
    session: Session, target: State, *, reason: str | None = None
) -> Session:
    allowed = {NEXT[session.state]} if session.state in NEXT else set()
    if session.state not in {State.READY, State.FAILED, State.NEEDS_INFO}:
        allowed |= {State.NEEDS_INFO, State.FAILED}
    if session.state == State.NEEDS_INFO:
        allowed = {
            State.ANALYZING,
            State.CONFIRMING,
            State.CLARIFYING,
            State.CALIBRATING,
            State.MEASURING,
        }
    if target not in allowed:
        raise ValueError(f"Invalid transition: {session.state.value} -> {target.value}")
    if target in {State.NEEDS_INFO, State.FAILED} and not (reason and reason.strip()):
        raise ValueError("Recovery states require a plain-language reason")
    return session.model_copy(
        update={
            "state": target,
            "pending_reason": reason,
            "revision": session.revision + 1,
            "updated_at": utcnow(),
        }
    )
