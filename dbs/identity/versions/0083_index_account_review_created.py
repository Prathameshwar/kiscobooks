"""Support the default review directory sort without a status filter."""

from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_account_review_created ON account_review (tenant_id, created_at, id)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_account_review_created ON account_review")
