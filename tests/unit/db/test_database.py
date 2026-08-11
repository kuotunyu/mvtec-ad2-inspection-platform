from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.models import InspectionImage, Job, Prediction
from inspection_platform.settings import Settings


def test_sqlite_connection_enables_safety_pragmas(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
    )
    session_factory = create_engine_and_session(settings)
    with session_factory() as session:
        assert session.scalar(text("PRAGMA journal_mode")) == "wal"
        assert session.scalar(text("PRAGMA foreign_keys")) == 1


def test_prediction_is_unique_per_inspection_image(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
    )
    sessions = create_engine_and_session(settings)
    job_id, image_id = str(uuid4()), str(uuid4())
    with sessions() as session, session.begin():
        session.add(
            Job(
                id=job_id,
                category="can",
                image_count=1,
                state="queued",
                created_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.add(
            InspectionImage(
                id=image_id,
                job_id=job_id,
                artifact_key="a" * 64,
                filename="image.png",
                media_type="image/png",
            )
        )
    with pytest.raises(IntegrityError), sessions() as session, session.begin():
        session.add(Prediction(id=str(uuid4()), image_id=image_id, payload={}))
        session.add(Prediction(id=str(uuid4()), image_id=image_id, payload={}))


def test_session_factory_upgrades_an_unstamped_legacy_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "legacy.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setenv("INSPECTION_DATABASE_URL", database_url)
    command.upgrade(Config("alembic.ini"), "0002_product_api")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))

    create_engine_and_session(
        Settings(
            database_url=database_url,
            artifact_root=tmp_path / "artifacts",
            model_registry_root=tmp_path / "models",
        )
    )

    inspector = inspect(engine)
    assert "worker_heartbeats" in inspector.get_table_names()
    assert "dedupe_key" in {column["name"] for column in inspector.get_columns("audit_events")}
