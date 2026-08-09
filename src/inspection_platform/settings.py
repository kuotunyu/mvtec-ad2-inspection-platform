from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_RUNTIME = Path(gettempdir()) / "mvtec-ad2-inspection-platform"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INSPECTION_", extra="ignore")

    database_url: str = f"sqlite:///{_DEFAULT_RUNTIME / 'inspection.db'}"
    artifact_root: Path = _DEFAULT_RUNTIME / "artifacts"
    model_registry_root: Path = _DEFAULT_RUNTIME / "models"
    max_upload_bytes: int = 25 * 1024 * 1024
    max_image_pixels: int = 100_000_000
    max_archive_files: int = 2_000
    max_archive_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    lease_seconds: int = 120
    heartbeat_seconds: int = 30

    @field_validator("artifact_root", "model_registry_root")
    @classmethod
    def _resolve_root(cls, value: Path) -> Path:
        path = value.expanduser().resolve()
        if path.exists() and not path.is_dir():
            raise ValueError(f"configured root is not a directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
        return path


__all__ = ["Settings"]
