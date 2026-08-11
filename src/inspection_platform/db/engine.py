from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from inspection_platform.settings import Settings

SessionFactory = sessionmaker[Session]

_CORE_TABLES = {
    "audit_events",
    "inspection_images",
    "jobs",
    "model_bundles",
    "predictions",
    "reviews",
}


def _sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _migration_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["database_url"] = database_url
    return config


def _unstamped_revision(engine: Engine) -> str | None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not tables:
        return None
    if "alembic_version" in tables:
        return "stamped"
    if not tables >= _CORE_TABLES:
        missing = ", ".join(sorted(_CORE_TABLES - tables))
        raise RuntimeError(f"existing database has an unrecognized schema; missing: {missing}")
    image_columns = {column["name"] for column in inspector.get_columns("inspection_images")}
    review_columns = {column["name"] for column in inspector.get_columns("reviews")}
    audit_columns = {column["name"] for column in inspector.get_columns("audit_events")}
    if "worker_heartbeats" in tables and "dedupe_key" in audit_columns:
        review_indexes = {item["name"] for item in inspector.get_indexes("reviews")}
        return (
            "0004_review_integrity"
            if "uq_reviews_image_id_revision" in review_indexes
            else "0003_worker_integrity"
        )
    if {"filename", "media_type"} <= image_columns and "revision" in review_columns:
        return "0002_product_api"
    return "0001_initial"


def _upgrade_schema(database_url: str) -> None:
    probe = create_engine(database_url, future=True)
    try:
        revision = _unstamped_revision(probe)
    finally:
        probe.dispose()
    config = _migration_config(database_url)
    if revision is not None and revision != "stamped":
        command.stamp(config, revision)
    command.upgrade(config, "head")


def create_engine_and_session(settings: Settings) -> SessionFactory:
    if settings.database_url.startswith("sqlite:///"):
        database_path = Path(settings.database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
    _upgrade_schema(settings.database_url)
    engine: Engine = create_engine(settings.database_url, future=True)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _sqlite_pragmas)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


__all__ = ["SessionFactory", "create_engine_and_session"]
