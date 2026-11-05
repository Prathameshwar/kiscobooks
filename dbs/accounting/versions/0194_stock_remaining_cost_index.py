"""Index only the remaining-layer selection grain; one DDL."""
from alembic import op

revision = "0194"
down_revision = "0193"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE INDEX ix_stock_cost_layer_remaining ON stock_cost_layer (tenant_id, company_id, pool_id, remaining_quantity, id)")

def downgrade() -> None:
    op.execute("DROP INDEX ix_stock_cost_layer_remaining ON stock_cost_layer")
