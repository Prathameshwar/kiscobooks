"""Index warehouse/bin retirement probes; one atomic DDL statement."""

from alembic import op

revision = "0210"
down_revision = "0209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_stock_position_location ON stock_position "
        "(tenant_id, company_id, warehouse_id, bin_key, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_stock_position_location ON stock_position")
