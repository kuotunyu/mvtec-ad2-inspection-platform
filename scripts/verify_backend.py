from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import text

from apps.api.main import create_app
from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.settings import Settings


def verify_backend() -> None:
    schema = create_app().openapi()
    if "/api/v1/jobs" not in schema["paths"] or "/metrics" not in schema["paths"]:
        raise RuntimeError("OpenAPI is missing required backend routes")
    with TemporaryDirectory(prefix="mvtec-ad2-backend-") as temporary:
        root = Path(temporary)
        settings = Settings(
            database_url=f"sqlite:///{root / 'inspection.db'}",
            artifact_root=root / "artifacts",
            model_registry_root=root / "models",
        )
        sessions = create_engine_and_session(settings)
        try:
            with sessions() as session:
                if session.scalar(text("PRAGMA foreign_keys")) != 1:
                    raise RuntimeError("SQLite foreign keys are disabled")
                if session.scalar(text("PRAGMA journal_mode")) != "wal":
                    raise RuntimeError("SQLite WAL is disabled")
        finally:
            sessions.kw["bind"].dispose()


def main() -> int:
    verify_backend()
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
