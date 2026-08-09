from __future__ import annotations

import pytest

from inspection_platform.reviews.service import ReviewConflict, ReviewService


def test_review_requires_current_revision() -> None:
    service = ReviewService()
    first = service.record("image-1", "ACCEPT", expected_revision=0)
    assert first.revision == 1
    with pytest.raises(ReviewConflict):
        service.record("image-1", "REJECT", expected_revision=0)
