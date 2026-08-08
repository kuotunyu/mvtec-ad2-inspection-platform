from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from inspection_platform.db.engine import create_engine_and_session
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
