"""Freeze the accepted commercial name and code without trusting client text."""

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_assignment ADD COLUMN source_code VARCHAR(40) NULL, ADD COLUMN source_name VARCHAR(160) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE voucher_assignment DROP COLUMN source_code, DROP COLUMN source_name")
