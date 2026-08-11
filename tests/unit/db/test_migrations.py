from __future__ import annotations

import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect, text

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.retention import delete_job_artifacts
from inspection_platform.settings import Settings


def test_clean_database_upgrades_through_all_revisions(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    worker_logger = logging.getLogger("inspection.worker")
    worker_logger.disabled = False
    database = tmp_path / "clean.db"
    monkeypatch.setenv("INSPECTION_DATABASE_URL", f"sqlite:///{database}")
    command.upgrade(Config("alembic.ini"), "head")
    columns = {
        item["name"]
        for item in inspect(create_engine(f"sqlite:///{database}")).get_columns("inspection_images")
    }
    assert {"filename", "media_type"} <= columns
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    assert "worker_heartbeats" in inspector.get_table_names()
    prediction_indexes = inspector.get_indexes("predictions")
    assert any(
        index["unique"] and index["column_names"] == ["image_id"] for index in prediction_indexes
    )
    review_indexes = inspector.get_indexes("reviews")
    assert any(
        index["unique"] and index["column_names"] == ["image_id", "revision"]
        for index in review_indexes
    )
    assert not worker_logger.disabled


def test_worker_integrity_migration_deduplicates_legacy_predictions(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    database = tmp_path / "legacy-duplicates.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setenv("INSPECTION_DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0002_product_api")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs "
                "(id, category, image_count, state, created_at, attempt) "
                "VALUES ('job-1', 'bottle', 1, 'COMPLETED', CURRENT_TIMESTAMP, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inspection_images "
                "(id, job_id, artifact_key, filename, media_type) "
                "VALUES ('image-1', 'job-1', 'artifact', 'image.png', 'image/png')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO predictions (id, image_id, payload) VALUES "
                "('a-error', 'image-1', '{\"error\": \"inference_failed\"}'), "
                "('z-evidence', 'image-1', "
                '\'{"anomaly_score": 0.7, "overlay_artifact_key": "abc"}\')'
            )
        )
        connection.execute(
            text(
                "INSERT INTO audit_events (id, action, resource_id, created_at) VALUES "
                "('audit-1', 'job.created', 'job-1', '2026-01-01 00:00:00'), "
                "('audit-2', 'job.created', 'job-1', '2026-01-01 00:00:01'), "
                "('audit-3', 'job.artifacts_deleted', 'job-1', '2026-01-01 00:00:02')"
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        predictions = (
            connection.execute(
                text("SELECT id, payload FROM predictions WHERE image_id = 'image-1'")
            )
            .mappings()
            .all()
        )
        audits = (
            connection.execute(text("SELECT id, action, dedupe_key FROM audit_events ORDER BY id"))
            .mappings()
            .all()
        )
    assert len(predictions) == 1
    assert predictions[0]["id"] == "z-evidence"
    payload = json.loads(predictions[0]["payload"])
    assert payload["anomaly_score"] == 0.7
    assert "error" not in payload
    assert len(audits) == 3
    assert audits[0]["dedupe_key"] == "job.created:job-1"
    assert audits[1]["dedupe_key"].startswith("legacy:job.created:job-1:")
    assert audits[2]["dedupe_key"] == "job.artifacts_deleted:job-1"

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    sessions = create_engine_and_session(
        Settings(
            database_url=database_url,
            artifact_root=artifact_root,
            model_registry_root=tmp_path / "models",
        )
    )
    delete_job_artifacts(artifact_root, sessions, "job-1")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM audit_events")) == 3


def test_review_integrity_migration_preserves_conflicting_legacy_decisions(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    database = tmp_path / "legacy-reviews.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setenv("INSPECTION_DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0003_worker_integrity")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO jobs "
                "(id, category, image_count, state, created_at, attempt) "
                "VALUES ('job-1', 'bottle', 1, 'COMPLETED', CURRENT_TIMESTAMP, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO inspection_images "
                "(id, job_id, artifact_key, filename, media_type) "
                "VALUES ('image-1', 'job-1', 'artifact', 'image.png', 'image/png')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO reviews "
                "(id, image_id, decision, note, created_at, revision) VALUES "
                "('review-a', 'image-1', 'ACCEPT', NULL, '2026-01-01 00:00:00', 1), "
                "('review-b', 'image-1', 'REJECT', NULL, '2026-01-01 00:00:01', 1), "
                "('review-c', 'image-1', 'UNCERTAIN', NULL, '2026-01-01 00:00:02', 2)"
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        reviews = connection.execute(
            text(
                "SELECT decision, revision FROM reviews "
                "WHERE image_id = 'image-1' ORDER BY revision"
            )
        ).all()
    assert reviews == [("ACCEPT", 1), ("REJECT", 2), ("UNCERTAIN", 3)]


def test_review_integrity_migration_resumes_after_index_creation(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    database = tmp_path / "partial-review-migration.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setenv("INSPECTION_DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0003_worker_integrity")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX uq_reviews_image_id_revision ON reviews (image_id, revision)")
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0004_review_integrity"
        )
