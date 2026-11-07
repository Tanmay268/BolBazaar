"""Engine and session factory."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        args = {"check_same_thread": False}
        in_memory = url in {"sqlite://", "sqlite:///:memory:"}
        if not in_memory:
            path = url.split("///", 1)[-1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args=args, poolclass=StaticPool if in_memory else None)

        @event.listens_for(engine, "connect")
        def _foreign_keys(dbapi_connection, _record):  # pragma: no cover - trivial
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        return engine
    # prepare_threshold=None keeps psycopg compatible with pooled (PgBouncer) endpoints such as Neon's -pooler host.
    return create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
