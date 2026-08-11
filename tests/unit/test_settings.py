from __future__ import annotations

import pytest
from pydantic import ValidationError

from inspection_platform.settings import Settings


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lease_seconds", 0),
        ("heartbeat_seconds", 0),
        ("retention_days", 0),
        ("retention_scan_seconds", 0),
        ("max_archive_files", 1_001),
    ],
)
def test_operational_limits_reject_unsafe_values(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_heartbeat_must_leave_lease_failure_margin() -> None:
    with pytest.raises(ValidationError, match="heartbeat interval"):
        Settings(lease_seconds=60, heartbeat_seconds=30)


def test_spool_capacity_covers_parser_staging_and_margin(tmp_path) -> None:
    settings = Settings(
        artifact_root=tmp_path / "artifacts",
        model_registry_root=tmp_path / "models",
        spool_root=tmp_path / "spool",
        max_archive_uncompressed_bytes=100,
        max_upload_bytes=25,
    )

    assert settings.minimum_spool_free_bytes == 225


def test_runtime_roots_must_be_distinct(tmp_path) -> None:
    with pytest.raises(ValidationError, match="roots must be distinct"):
        Settings(
            artifact_root=tmp_path / "shared",
            model_registry_root=tmp_path / "models",
            spool_root=tmp_path / "shared",
        )
