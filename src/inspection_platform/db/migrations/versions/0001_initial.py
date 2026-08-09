"""initial durable inspection schema"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("attempt", sa.Integer(), nullable=False),
    )
    op.create_table(
        "inspection_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("artifact_key", sa.String(255), nullable=False),
    )
    op.create_index("ix_inspection_images_job_id", "inspection_images", ["job_id"])
    op.create_table(
        "predictions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("image_id", sa.String(36), sa.ForeignKey("inspection_images.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("image_id", sa.String(36), sa.ForeignKey("inspection_images.id"), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_table(
        "model_bundles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("family", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("model_bundles")
    op.drop_index("ix_audit_events_resource_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("reviews")
    op.drop_table("predictions")
    op.drop_index("ix_inspection_images_job_id", table_name="inspection_images")
    op.drop_table("inspection_images")
    op.drop_table("jobs")
