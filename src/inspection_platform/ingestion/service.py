from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

from inspection_platform.db.repositories import Repositories
from inspection_platform.storage.artifacts import ArtifactRef, ArtifactStore

from .images import validate_image


@dataclass(frozen=True)
class UploadStream:
    filename: str
    stream: BinaryIO


@dataclass(frozen=True)
class JobRead:
    id: str
    category: str
    image_count: int
    artifacts: tuple[ArtifactRef, ...]


class IngestionService:
    def __init__(self, repositories: Repositories, artifacts: ArtifactStore) -> None:
        self.repositories = repositories
        self.artifacts = artifacts

    def create_job(self, category: str, uploads: Sequence[UploadStream]) -> JobRead:
        if not uploads:
            raise ValueError("at least one upload is required")
        refs: list[ArtifactRef] = []
        for upload in uploads:
            image = validate_image(
                upload.stream, filename=upload.filename, max_bytes=25 * 1024 * 1024
            )
            refs.append(
                self.artifacts.put_stream(BytesIO(image.content), media_type=image.media_type)
            )
        job = self.repositories.jobs.create(category=category, image_count=len(refs))
        return JobRead(job.id, job.category, job.image_count, tuple(refs))


__all__ = ["IngestionService", "JobRead", "UploadStream"]
