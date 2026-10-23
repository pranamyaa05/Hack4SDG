from backend.contracts import Session, State, utcnow
from backend.storage import RevisionConflict, SessionStore

from .models import Workspace


class MeasurementStore:
    def __init__(self, sessions: SessionStore):
        self.sessions = sessions
        with sessions.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS measurement_workspaces (session_id TEXT PRIMARY KEY, body TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS measurement_images (session_id TEXT NOT NULL, name TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY(session_id, name))"
            )

    def load(self, session_id: str):
        with self.sessions.connect() as db:
            db.execute("BEGIN")
            row = db.execute(
                "SELECT body FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            payload = db.execute(
                "SELECT body FROM measurement_workspaces WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return Session.model_validate_json(row[0]), Workspace.model_validate_json(
            payload[0]
        ) if payload else None

    def save(
        self,
        session: Session,
        workspace: Workspace,
        expected_revision: int,
        *,
        state: State | None = None,
        images: dict | None = None,
        clear_images=False,
    ):
        updated = session.model_copy(
            update={
                "revision": expected_revision + 1,
                "updated_at": utcnow(),
                "state": state or session.state,
                "pending_reason": None,
            }
        )
        with self.sessions.connect() as db:
            result = db.execute(
                "UPDATE sessions SET revision = ?, body = ? WHERE id = ? AND revision = ?",
                (
                    updated.revision,
                    updated.model_dump_json(),
                    session.id,
                    expected_revision,
                ),
            )
            if result.rowcount != 1:
                raise RevisionConflict("Session changed; reload and retry")
            db.execute(
                "INSERT INTO measurement_workspaces VALUES (?, ?) ON CONFLICT(session_id) DO UPDATE SET body = excluded.body",
                (session.id, workspace.model_dump_json()),
            )
            if clear_images:
                db.execute(
                    "DELETE FROM measurement_images WHERE session_id = ?", (session.id,)
                )
            for name, data in (images or {}).items():
                db.execute(
                    "INSERT INTO measurement_images VALUES (?, ?, ?) ON CONFLICT(session_id,name) DO UPDATE SET data = excluded.data",
                    (session.id, name, data),
                )
        return updated

    def image(self, session_id: str, name: str):
        with self.sessions.connect() as db:
            row = db.execute(
                "SELECT data FROM measurement_images WHERE session_id = ? AND name = ?",
                (session_id, name),
            ).fetchone()
        return row[0] if row else None
