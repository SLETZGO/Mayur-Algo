"""FastAPI application factory with database-backed signal intake."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from nifty_algo.api.dashboard import router as dashboard_router
from nifty_algo.api.fyers import router as fyers_router
from nifty_algo.api.health import router as health_router
from nifty_algo.api.webhook import router as webhook_router
from nifty_algo.config import AppConfig, config_from_environment
from nifty_algo.data.database import create_database_engine, create_session_factory
from nifty_algo.data.models import Base


def create_app(
    config: AppConfig | None = None,
    *,
    session_factory: sessionmaker | None = None,
    create_schema: bool = False,
) -> FastAPI:
    settings = config or config_from_environment()

    app = FastAPI(title="Nifty Algo Signal Intake", version="0.1.0")
    # Local Next.js development origins only. Production deployments should set
    # their own explicit origins when deployment configuration is introduced.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    if session_factory is None:
        engine = create_database_engine(settings.database_url)
        session_factory = create_session_factory(engine)
        app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.config = settings
    app.state.webhook_secret = settings.webhook_secret
    app.state.webhook_max_payload_bytes = settings.webhook_max_payload_bytes
    if create_schema:
        engine = getattr(app.state, "engine", None) or session_factory.kw.get("bind")
        if engine is None:
            raise ValueError("create_schema requires a session factory bound to an Engine")
        Base.metadata.create_all(engine)
    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(fyers_router)
    app.include_router(webhook_router)
    return app
