"""Keep the reviewed attribution-change reason on the immutable voucher revision."""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voucher_revision ADD COLUMN assignment_override_reason VARCHAR(500) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE voucher_revision DROP COLUMN assignment_override_reason")
