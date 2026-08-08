from __future__ import annotations

from pathlib import Path

import pytest

from experiments.submission.build import (
    PrivateManifest,
    PublicBoundaryError,
    SubmissionBuilder,
)


def test_private_predictions_are_never_written_under_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    manifest = PrivateManifest(images=(("can", "test_private", "000_regular"),))

    with pytest.raises(PublicBoundaryError, match="outside repository"):
        SubmissionBuilder(manifest=manifest, repository_root=repo_root).build(
            output_dir=repo_root / "reports",
            predictions=(),
        )


def test_manifest_rejects_duplicate_image_identity() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        PrivateManifest(
            images=(
                ("can", "test_private", "000_regular"),
                ("can", "test_private", "000_regular"),
            )
        )
