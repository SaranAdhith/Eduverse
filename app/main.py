"""FastAPI app factory + lifespan (DOC_01 §2, §7, §8.3)."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import dispose_engine, get_engine
from app.logging import configure_logging
from app.modules.content.router import router as content_router
from app.modules.graph.router import router as graph_router
from app.modules.mastery.router import router as mastery_router
from app.modules.participants.router import router as participants_router
from app.modules.planner.router import router as planner_router
from app.modules.questions.router import router as diagnostic_router
from app.modules.study import events as study_events
from app.modules.study.router import router as study_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    # DOC_08 §4: dual-write events to the DB via a write-behind flush loop.
    study_events.install()
    study_events.start_flusher()
    structlog.get_logger("app").info("startup", env=settings.env)
    try:
        yield
    finally:
        await study_events.stop_flusher()
        await dispose_engine()
        structlog.get_logger("app").info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="Eduverse", version="0.1.0", lifespan=lifespan)

    # Allow the participant frontend (a different origin) to call the API, and to
    # read the X-Request-ID we echo back.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # DOC_01 §7: every record carries a per-request id (and participant_code
        # once get_participant binds it).
        structlog.contextvars.clear_contextvars()
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        db_status = "ok"
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            db_status = "error"
        return {"status": "ok", "db": db_status}

    app.include_router(participants_router)
    app.include_router(graph_router)
    app.include_router(diagnostic_router)
    app.include_router(mastery_router)
    app.include_router(planner_router)
    app.include_router(content_router)
    app.include_router(study_router)
    return app


app = create_app()
