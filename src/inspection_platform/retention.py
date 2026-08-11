from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from inspection_platform.db.models import AuditEvent, InspectionImage, Job, Prediction
from inspection_platform.storage.artifacts import artifact_store_lock, artifact_store_lock_path


class DeletionScopeError(ValueError):
    """Raised when an artifact target cannot be proven to remain under its root."""


@dataclass(frozen=True)
class DeletionResult:
    deleted_files: int


@dataclass(frozen=True)
class RetentionResult:
    deleted_jobs: int
    deleted_files: int
    failed_jobs: int = 0
    failed_job_ids: tuple[str, ...] = ()


def expired_artifacts(root: Path, cutoff: datetime) -> tuple[Path, ...]:
    resolved = root.expanduser().resolve(strict=True)
    normalized_cutoff = cutoff.astimezone(UTC)
    expired = []
    for path in resolved.rglob("*"):
        if not path.is_file():
            continue
        if path == artifact_store_lock_path(resolved):
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified < normalized_cutoff:
            expired.append(path)
    return tuple(sorted(expired))


def delete_job_artifacts(
    root: Path, session_factory: Callable[[], Session], job_id: str
) -> DeletionResult:
    resolved_root = root.expanduser().resolve(strict=True)
    with artifact_store_lock(resolved_root):
        return _delete_job_artifacts_locked(resolved_root, session_factory, job_id)


def _delete_job_artifacts_locked(
    resolved_root: Path, session_factory: Callable[[], Session], job_id: str
) -> DeletionResult:
    deleted = 0
    with session_factory() as session, session.begin():
        images = list(
            session.scalars(select(InspectionImage).where(InspectionImage.job_id == job_id))
        )
        image_ids = {image.id for image in images}
        predictions = (
            list(session.scalars(select(Prediction).where(Prediction.image_id.in_(image_ids))))
            if image_ids
            else []
        )
        candidate_keys = {image.artifact_key for image in images}
        for prediction in predictions:
            for key in ("anomaly_map_artifact_key", "overlay_artifact_key"):
                value = prediction.payload.get(key)
                if isinstance(value, str):
                    candidate_keys.add(value)

        tombstoned_jobs = set(
            session.scalars(
                select(AuditEvent.resource_id).where(AuditEvent.action == "job.artifacts_deleted")
            )
        )
        other_images = list(
            session.scalars(select(InspectionImage).where(InspectionImage.job_id != job_id))
        )
        active_images = [image for image in other_images if image.job_id not in tombstoned_jobs]
        active_image_ids = {image.id for image in active_images}
        referenced_keys = {image.artifact_key for image in active_images}
        if active_image_ids:
            for prediction in session.scalars(
                select(Prediction).where(Prediction.image_id.in_(active_image_ids))
            ):
                for key in ("anomaly_map_artifact_key", "overlay_artifact_key"):
                    value = prediction.payload.get(key)
                    if isinstance(value, str):
                        referenced_keys.add(value)

        for artifact_key in sorted(candidate_keys):
            candidate = resolved_root / artifact_key[:2] / artifact_key
            if candidate.is_symlink():
                raise DeletionScopeError("artifact target is a symbolic link")
            try:
                candidate.resolve(strict=False).relative_to(resolved_root)
            except ValueError as exc:
                raise DeletionScopeError("artifact target escapes configured root") from exc
            if artifact_key not in referenced_keys and candidate.is_file():
                candidate.unlink()
                deleted += 1
        session.execute(
            sqlite_insert(AuditEvent)
            .values(
                id=str(uuid4()),
                action="job.artifacts_deleted",
                resource_id=job_id,
                created_at=datetime.now(UTC),
                dedupe_key=f"job.artifacts_deleted:{job_id}",
            )
            .on_conflict_do_nothing(index_elements=[AuditEvent.dedupe_key])
        )
    return DeletionResult(deleted)


def purge_orphan_artifacts(
    root: Path,
    session_factory: Callable[[], Session],
    cutoff: datetime,
) -> int:
    resolved_root = root.expanduser().resolve(strict=True)
    normalized_cutoff = cutoff.astimezone(UTC)
    deleted = 0
    with artifact_store_lock(resolved_root):
        with session_factory() as session:
            images = list(session.scalars(select(InspectionImage)))
            referenced_keys = {image.artifact_key for image in images}
            for prediction in session.scalars(select(Prediction)):
                for key in ("anomaly_map_artifact_key", "overlay_artifact_key"):
                    value = prediction.payload.get(key)
                    if isinstance(value, str):
                        referenced_keys.add(value)
        for candidate in sorted(path for path in resolved_root.rglob("*") if path.is_file()):
            if candidate == artifact_store_lock_path(resolved_root):
                continue
            if candidate.is_symlink():
                raise DeletionScopeError("orphan artifact target is a symbolic link")
            try:
                relative = candidate.resolve(strict=False).relative_to(resolved_root)
            except ValueError as exc:
                raise DeletionScopeError("orphan artifact target escapes configured root") from exc
            modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
            artifact_key = relative.name if len(relative.parts) == 2 else None
            if modified < normalized_cutoff and artifact_key not in referenced_keys:
                candidate.unlink()
                deleted += 1
    return deleted


def purge_expired_jobs(
    root: Path,
    session_factory: Callable[[], Session],
    cutoff: datetime,
) -> RetentionResult:
    normalized_cutoff = cutoff.astimezone(UTC).replace(tzinfo=None)
    terminal_states = ("COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED")
    with session_factory() as session:
        tombstoned_jobs = set(
            session.scalars(
                select(AuditEvent.resource_id).where(AuditEvent.action == "job.artifacts_deleted")
            )
        )
        job_ids = tuple(
            session.scalars(
                select(Job.id)
                .where(Job.state.in_(terminal_states), Job.created_at < normalized_cutoff)
                .order_by(Job.created_at)
            )
        )
    pending = tuple(job_id for job_id in job_ids if job_id not in tombstoned_jobs)
    deleted_jobs = 0
    deleted_files = 0
    failed_jobs = 0
    failed_job_ids: list[str] = []
    for job_id in pending:
        try:
            result = delete_job_artifacts(root, session_factory, job_id)
        except (DeletionScopeError, OSError):
            failed_jobs += 1
            failed_job_ids.append(job_id)
            continue
        deleted_jobs += 1
        deleted_files += result.deleted_files
    deleted_files += purge_orphan_artifacts(root, session_factory, cutoff)
    return RetentionResult(
        deleted_jobs=deleted_jobs,
        deleted_files=deleted_files,
        failed_jobs=failed_jobs,
        failed_job_ids=tuple(failed_job_ids),
    )


__all__ = [
    "DeletionResult",
    "DeletionScopeError",
    "RetentionResult",
    "delete_job_artifacts",
    "expired_artifacts",
    "purge_expired_jobs",
    "purge_orphan_artifacts",
]
