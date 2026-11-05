"""Index account currency-mode-filtered code pages; one DDL statement."""

from alembic import op

revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE account ADD INDEX ix_account_currency_mode (tenant_id, company_id, currency_mode, code, id)"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE account DROP INDEX ix_account_currency_mode")
