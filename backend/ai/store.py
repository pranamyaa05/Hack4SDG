from backend.contracts import Session, utcnow
from backend.storage import RevisionConflict, SessionStore

from .models import AnalysisWorkspace


class AnalysisStore:
    def __init__(self, sessions: SessionStore):
        self.sessions = sessions
        with sessions.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS analysis_workspaces (session_id TEXT PRIMARY KEY, body TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS analysis_images (session_id TEXT NOT NULL, name TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY(session_id,name))"
            )

    def load(self, session_id):
        with self.sessions.connect() as db:
            db.execute("BEGIN")
            row = db.execute(
                "SELECT body FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            payload = db.execute(
                "SELECT body FROM analysis_workspaces WHERE session_id=?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return Session.model_validate_json(
            row[0]
        ), AnalysisWorkspace.model_validate_json(
            payload[0]
        ) if payload else AnalysisWorkspace()

    def save(self, session, workspace, expected_revision, *, state, images=None):
        updated = session.model_copy(
            update={
                "revision": expected_revision + 1,
                "state": state,
                "updated_at": utcnow(),
                "pending_reason": None,
            }
        )
        with self.sessions.connect() as db:
            if (
                db.execute(
                    "UPDATE sessions SET revision=?,body=? WHERE id=? AND revision=?",
                    (
                        updated.revision,
                        updated.model_dump_json(),
                        session.id,
                        expected_revision,
                    ),
                ).rowcount
                != 1
            ):
                raise RevisionConflict("Session changed; reload and retry")
            db.execute(
                "INSERT INTO analysis_workspaces VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET body=excluded.body",
                (session.id, workspace.model_dump_json()),
            )
            for name, data in (images or {}).items():
                db.execute(
                    "INSERT INTO analysis_images VALUES (?,?,?) ON CONFLICT(session_id,name) DO UPDATE SET data=excluded.data",
                    (session.id, name, data),
                )
        return updated

    def image(self, session_id, name):
        with self.sessions.connect() as db:
            row = db.execute(
                "SELECT data FROM analysis_images WHERE session_id=? AND name=?",
                (session_id, name),
            ).fetchone()
        return row[0] if row else None

    def has_measurements(self, session_id):
        with self.sessions.connect() as db:
            return (
                db.execute(
                    "SELECT 1 FROM measurement_workspaces WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                is not None
            )
