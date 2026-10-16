"""SQLAlchemy engine/session setup, isolated from API and strategy code."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_database_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:") and ":memory:" not in database_url:
        database_path = database_url.removeprefix("sqlite:///")
        if database_path and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"check_same_thread": False} if database_url.startswith("sqlite:") else {}
    poolclass = StaticPool if database_url in {"sqlite://", "sqlite:///:memory:"} else None
    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=kwargs,
        **({"poolclass": poolclass} if poolclass is not None else {}),
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
