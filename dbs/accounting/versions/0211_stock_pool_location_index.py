"""Index warehouse quantity/value clearance probes; one atomic DDL statement."""

from alembic import op

revision = "0211"
down_revision = "0210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_stock_cost_pool_location ON stock_cost_pool "
        "(tenant_id, company_id, warehouse_id, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_stock_cost_pool_location ON stock_cost_pool")
