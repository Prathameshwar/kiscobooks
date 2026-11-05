"""Dedicated native count action; one atomic ALTER."""

from alembic import op
from sqlalchemy import text

revision = "0225"
down_revision = "0224"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE stock_posting
        DROP CHECK ck_stock_posting_stock_posting_action,
        ADD CONSTRAINT ck_stock_posting_stock_posting_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH',
            'TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','COUNT','REVERSAL'))""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_posting WHERE action = 'COUNT' LIMIT 1")).first():
        raise RuntimeError("archive retained count posting history before downgrade")
    op.execute("""ALTER TABLE stock_posting
        DROP CHECK ck_stock_posting_stock_posting_action,
        ADD CONSTRAINT ck_stock_posting_stock_posting_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH',
            'TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','REVERSAL'))""")
