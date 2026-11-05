"""Index kind-filtered account code pages; one DDL statement."""

from alembic import op

revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE account ADD INDEX ix_account_kind (tenant_id, company_id, kind, code, id)"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE account DROP INDEX ix_account_kind")
