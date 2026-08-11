from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_RUNTIME = Path(gettempdir()) / "mvtec-ad2-inspection-platform"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INSPECTION_", extra="ignore")

    database_url: str = f"sqlite:///{_DEFAULT_RUNTIME / 'inspection.db'}"
    artifact_root: Path = _DEFAULT_RUNTIME / "artifacts"
    model_registry_root: Path = _DEFAULT_RUNTIME / "models"
    spool_root: Path = _DEFAULT_RUNTIME / "spool"
    inference_device: str = "cpu"
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=100_000_000, gt=0)
    max_archive_files: int = Field(default=1_000, gt=0, le=1_000)
    max_archive_uncompressed_bytes: int = Field(default=2 * 1024 * 1024 * 1024, gt=0)
    lease_seconds: int = Field(default=120, gt=0)
    heartbeat_seconds: int = Field(default=30, gt=0)
    retention_days: int = Field(default=7, gt=0)
    retention_scan_seconds: int = Field(default=3_600, gt=0)

    @model_validator(mode="after")
    def _validate_lease_margin(self) -> Settings:
        if self.heartbeat_seconds * 2 >= self.lease_seconds:
            raise ValueError("heartbeat interval must be less than half the lease duration")
        roots = {self.artifact_root, self.model_registry_root, self.spool_root}
        if len(roots) != 3:
            raise ValueError("artifact, model registry, and spool roots must be distinct")
        return self

    @field_validator("artifact_root", "model_registry_root", "spool_root")
    @classmethod
    def _resolve_root(cls, value: Path) -> Path:
        path = value.expanduser().resolve()
        if path.exists() and not path.is_dir():
            raise ValueError(f"configured root is not a directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def minimum_spool_free_bytes(self) -> int:
        """Capacity for parser and validation copies plus one-file headroom."""
        return 2 * self.max_archive_uncompressed_bytes + self.max_upload_bytes


__all__ = ["Settings"]
