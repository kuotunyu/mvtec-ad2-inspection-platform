"""Add product API image metadata and review revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0002_product_api"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspection_images",
        sa.Column("filename", sa.String(length=255), nullable=False, server_default="image"),
    )
    op.add_column(
        "inspection_images",
        sa.Column(
            "media_type",
            sa.String(length=64),
            nullable=False,
            server_default="application/octet-stream",
        ),
    )
    op.add_column(
        "reviews", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )


def downgrade() -> None:
    op.drop_column("reviews", "revision")
    op.drop_column("inspection_images", "media_type")
    op.drop_column("inspection_images", "filename")
