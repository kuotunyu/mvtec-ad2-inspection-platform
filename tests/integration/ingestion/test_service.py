from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from inspection_platform.db.engine import create_engine_and_session
from inspection_platform.db.repositories import Repositories
from inspection_platform.ingestion.service import IngestionService, UploadStream
from inspection_platform.settings import Settings
from inspection_platform.storage.artifacts import ArtifactStore


def test_ingestion_creates_job_and_content_addressed_artifact(tmp_path: Path) -> None:
    image = Image.new("RGB", (4, 4), "blue")
    stream = BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'inspection.db'}",
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
    )
    repositories = Repositories(create_engine_and_session(settings))
    result = IngestionService(repositories, ArtifactStore(settings.artifact_root)).create_job(
        "can", [UploadStream("sample.png", stream)]
    )
    assert result.category == "can"
    assert result.image_count == 1
    assert result.artifacts[0].path.exists()
