"""SQLite storage with optimistic concurrency for stage updates."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .contracts import Session


class RevisionConflict(Exception):
    pass


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, session: Session) -> Session:
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (session.id, session.revision, session.model_dump_json()),
            )
        return session

    def get(self, session_id: str) -> Session | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT body FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return Session.model_validate_json(row[0]) if row else None

    def save(self, session: Session, *, expected_revision: int) -> Session:
        if session.revision != expected_revision + 1:
            raise RevisionConflict("Updates must advance the revision exactly once")
        with self.connect() as db:
            result = db.execute(
                "UPDATE sessions SET revision = ?, body = ? WHERE id = ? AND revision = ?",
                (
                    session.revision,
                    session.model_dump_json(),
                    session.id,
                    expected_revision,
                ),
            )
            if result.rowcount != 1:
                raise RevisionConflict("Session changed; reload before retrying")
        return session
