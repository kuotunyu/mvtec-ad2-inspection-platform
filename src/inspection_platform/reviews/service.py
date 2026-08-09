from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

ReviewDecision = Literal["ACCEPT", "REJECT", "UNCERTAIN"]


class ReviewConflict(RuntimeError):
    """Raised when optimistic review revision does not match."""


@dataclass(frozen=True)
class ReviewRecord:
    image_id: str
    decision: ReviewDecision
    revision: int
    created_at: datetime


class ReviewService:
    def __init__(self) -> None:
        self._latest: dict[str, ReviewRecord] = {}

    def record(
        self, image_id: str, decision: ReviewDecision, *, expected_revision: int
    ) -> ReviewRecord:
        current = self._latest.get(image_id)
        revision = 0 if current is None else current.revision
        if revision != expected_revision:
            raise ReviewConflict("review revision conflict")
        result = ReviewRecord(image_id, decision, revision + 1, datetime.now(UTC))
        self._latest[image_id] = result
        return result


__all__ = ["ReviewConflict", "ReviewRecord", "ReviewService"]
