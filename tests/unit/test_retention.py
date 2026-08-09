from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from inspection_platform.retention import expired_artifacts


def test_retention_only_selects_files_older_than_cutoff(tmp_path: Path) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    now = datetime.now(UTC)
    old_time = (now - timedelta(days=10)).timestamp()
    old.touch()
    os.utime(old, (old_time, old_time))
    assert expired_artifacts(tmp_path, now - timedelta(days=5)) == (old,)
