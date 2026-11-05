"""Bound active physical cohort selection independently of exhausted history; one DDL."""
from alembic import op

revision = "0195"
down_revision = "0194"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE INDEX ix_stock_origin_balance_remaining ON stock_origin_balance (tenant_id, company_id, position_id, quantity, id)")

def downgrade() -> None:
    op.execute("DROP INDEX ix_stock_origin_balance_remaining ON stock_origin_balance")
