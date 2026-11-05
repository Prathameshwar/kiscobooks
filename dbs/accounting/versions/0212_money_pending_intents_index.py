"""Index bounded inflight posting probes; one atomic DDL statement."""

from alembic import op

revision = "0212"
down_revision = "0211"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_money_intent_pending ON voucher_money_intent "
        "(tenant_id, company_id, status, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_money_intent_pending ON voucher_money_intent")
