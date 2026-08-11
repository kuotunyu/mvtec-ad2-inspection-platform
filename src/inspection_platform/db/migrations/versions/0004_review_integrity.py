"""Enforce optimistic review revision integrity."""

from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "0004_review_integrity"
down_revision = "0003_worker_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("reviews")}
    if "uq_reviews_image_id_revision" in indexes:
        return
    rows = bind.execute(
        sa.text(
            "SELECT id, image_id, revision, created_at FROM reviews "
            "ORDER BY image_id, revision, created_at, id"
        )
    ).mappings()
    grouped: dict[str, list[sa.RowMapping]] = defaultdict(list)
    for row in rows:
        grouped[str(row["image_id"])].append(row)
    for reviews in grouped.values():
        for offset, row in enumerate(reviews, start=1):
            bind.execute(
                sa.text("UPDATE reviews SET revision = :revision WHERE id = :id"),
                {"id": row["id"], "revision": -offset},
            )
        for revision, row in enumerate(reviews, start=1):
            bind.execute(
                sa.text("UPDATE reviews SET revision = :revision WHERE id = :id"),
                {"id": row["id"], "revision": revision},
            )
    op.create_index(
        "uq_reviews_image_id_revision", "reviews", ["image_id", "revision"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_reviews_image_id_revision", table_name="reviews")
