from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from inspection_platform.db.models import AuditEvent, InspectionImage


class DeletionScopeError(ValueError):
    """Raised when an artifact target cannot be proven to remain under its root."""


@dataclass(frozen=True)
class DeletionResult:
    deleted_files: int


def expired_artifacts(root: Path, cutoff: datetime) -> tuple[Path, ...]:
    resolved = root.expanduser().resolve(strict=True)
    normalized_cutoff = cutoff.astimezone(UTC)
    expired = []
    for path in resolved.rglob("*"):
        if not path.is_file():
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified < normalized_cutoff:
            expired.append(path)
    return tuple(sorted(expired))


def delete_job_artifacts(
    root: Path, session_factory: Callable[[], Session], job_id: str
) -> DeletionResult:
    resolved_root = root.expanduser().resolve(strict=True)
    deleted = 0
    with session_factory() as session, session.begin():
        images = list(
            session.scalars(select(InspectionImage).where(InspectionImage.job_id == job_id))
        )
        for image in images:
            candidate = resolved_root / image.artifact_key[:2] / image.artifact_key
            if candidate.is_symlink():
                raise DeletionScopeError("artifact target is a symbolic link")
            try:
                candidate.resolve(strict=False).relative_to(resolved_root)
            except ValueError as exc:
                raise DeletionScopeError("artifact target escapes configured root") from exc
            references = session.scalar(
                select(func.count())
                .select_from(InspectionImage)
                .where(
                    InspectionImage.artifact_key == image.artifact_key,
                    InspectionImage.job_id != job_id,
                )
            )
            if not references and candidate.is_file():
                candidate.unlink()
                deleted += 1
        tombstone = session.scalar(
            select(AuditEvent).where(
                AuditEvent.resource_id == job_id,
                AuditEvent.action == "job.artifacts_deleted",
            )
        )
        if tombstone is None:
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    action="job.artifacts_deleted",
                    resource_id=job_id,
                    created_at=datetime.now(UTC),
                )
            )
    return DeletionResult(deleted)


__all__ = [
    "DeletionResult",
    "DeletionScopeError",
    "delete_job_artifacts",
    "expired_artifacts",
]
