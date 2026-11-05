"""Existing epochs remain reference-only; rebuilt epochs opt into derived queries."""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE report_source_epoch ADD COLUMN query_version INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE report_source_epoch DROP COLUMN query_version")
