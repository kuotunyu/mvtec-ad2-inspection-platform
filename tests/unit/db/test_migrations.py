from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect


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
    assert not worker_logger.disabled
