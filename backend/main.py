import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .ai.api import router as analysis_router
from .ai.providers import AISettings
from .ai.service import AnalysisService
from .ai.store import AnalysisStore
from .contracts import DesignSpec, Session, SessionCreate
from .design.api import router as design_router
from .design.store import DesignStore
from .measurement.api import router as measurement_router
from .measurement.store import MeasurementStore
from .storage import SessionStore


def create_app(
    database_path: Path | None = None,
    *,
    ai_settings: AISettings | None = None,
    ai_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    path = (
        database_path or Path(os.environ.get("REFIT_DATA_DIR", "var")) / "refit.sqlite3"
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.sessions = SessionStore(path)
        app.state.measurements = MeasurementStore(app.state.sessions)
        app.state.analysis = AnalysisStore(app.state.sessions)
        app.state.designs = DesignStore(app.state.sessions)
        app.state.output_root = path.parent / "designs"
        with app.state.sessions.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS refit_links (session_id TEXT PRIMARY KEY, parent_design_id TEXT NOT NULL)"
            )
        with httpx.Client(
            transport=ai_transport, trust_env=False, follow_redirects=False
        ) as client:
            app.state.ai_service = AnalysisService(
                ai_settings or AISettings.from_env(), client
            )
            yield

    app = FastAPI(title="ReFit", version="0.1.0", lifespan=lifespan)

    app.include_router(measurement_router)
    app.include_router(analysis_router)
    app.include_router(design_router)

    @app.get("/api/health")
    def health(request: Request):
        with request.app.state.sessions.connect() as db:
            db.execute("SELECT 1")
        return {
            "status": "ok",
            "stage": "design",
            "schema_version": "1.0.0",
            "capabilities": {
                "sessions": True,
                "analysis": True,
                "measurement": True,
                "cad": __import__("importlib.util", fromlist=["find_spec"]).find_spec(
                    "cadquery"
                )
                is not None,
            },
        }

    @app.post("/api/sessions", response_model=Session, status_code=201)
    def create_session(body: SessionCreate, request: Request):
        return request.app.state.sessions.create(Session(**body.model_dump()))

    @app.get("/api/sessions/{session_id}", response_model=Session)
    def get_session(session_id: UUID, request: Request):
        session = request.app.state.sessions.get(str(session_id))
        if session is None:
            raise HTTPException(404, "Session not found")
        return session

    @app.get("/api/contracts/design-spec")
    def design_schema():
        return DesignSpec.model_json_schema()

    frontend = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/app", StaticFiles(directory=frontend, html=True), name="studio")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app/" if frontend.is_dir() else "/docs")

    return app


app = create_app()
