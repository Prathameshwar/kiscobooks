"""Index account currency-filtered code pages; one DDL statement."""

from alembic import op

revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE account ADD INDEX ix_account_currency (tenant_id, company_id, currency, code, id)"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE account DROP INDEX ix_account_currency")
