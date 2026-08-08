"""initial durable inspection schema"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from inspection_platform.db.models import Base

    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    from inspection_platform.db.models import Base

    Base.metadata.drop_all(op.get_bind())
