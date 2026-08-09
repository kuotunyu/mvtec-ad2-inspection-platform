from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


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


__all__ = ["expired_artifacts"]
