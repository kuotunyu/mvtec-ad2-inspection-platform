from __future__ import annotations

from pathlib import Path

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.repositories import Repositories
from inspection_platform.settings import Settings


def test_job_creation_and_audit_are_atomic(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
    )
    session_factory = create_engine_and_session(settings)
    repositories = Repositories(session_factory)
    job = repositories.jobs.create(category="can", image_count=2)
    events = repositories.audit.list_for_resource(job.id)
    assert [(event.action, event.resource_id) for event in events] == [("job.created", job.id)]
