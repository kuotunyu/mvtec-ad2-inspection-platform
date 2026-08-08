from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from inspection_platform.settings import Settings

from .models import Base

SessionFactory = sessionmaker[Session]


def _sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_engine_and_session(settings: Settings) -> SessionFactory:
    if settings.database_url.startswith("sqlite:///"):
        database_path = Path(settings.database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
    engine: Engine = create_engine(settings.database_url, future=True)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _sqlite_pragmas)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


__all__ = ["SessionFactory", "create_engine_and_session"]
