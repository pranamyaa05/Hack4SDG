import json

from backend.contracts import State, utcnow
from backend.storage import RevisionConflict


class DesignStore:
    def __init__(self, sessions):
        self.sessions = sessions
        with sessions.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS designs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS design_feedback (design_id TEXT PRIMARY KEY, body TEXT NOT NULL)"
            )

    def publish(self, session, spec, record):
        updated = session.model_copy(
            update={
                "revision": session.revision + 1,
                "state": State.READY,
                "updated_at": utcnow(),
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
                        session.revision,
                    ),
                ).rowcount
                != 1
            ):
                raise RevisionConflict("Session changed during generation; reload")
            db.execute(
                "INSERT INTO designs VALUES (?,?,?,?)",
                (
                    spec.design_id,
                    session.id,
                    json.dumps(record),
                    spec.created_at.isoformat(),
                ),
            )
        return updated

    def get(self, design_id):
        with self.sessions.connect() as db:
            row = db.execute(
                "SELECT body FROM designs WHERE id=?", (design_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        with self.sessions.connect() as db:
            rows = db.execute(
                "SELECT d.body,f.body FROM designs d LEFT JOIN design_feedback f ON d.id=f.design_id ORDER BY d.created_at DESC"
            ).fetchall()
        return [
            dict(json.loads(d), feedback=json.loads(f) if f else None) for d, f in rows
        ]

    def feedback(self, design_id, body):
        with self.sessions.connect() as db:
            db.execute(
                "INSERT INTO design_feedback VALUES (?,?) ON CONFLICT(design_id) DO UPDATE SET body=excluded.body",
                (design_id, json.dumps(body)),
            )
