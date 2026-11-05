"""B24: a goods Purchase bill's stock posting; one atomic ALTER."""

from alembic import op
from sqlalchemy import text

revision = "0231"
down_revision = "0230"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE stock_posting
        DROP CHECK ck_stock_posting_stock_posting_action,
        ADD CONSTRAINT ck_stock_posting_stock_posting_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH',
            'TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','COUNT','PURCHASE_INVOICE',
            'REVERSAL'))""")


def downgrade() -> None:
    if op.get_bind().execute(
        text("SELECT id FROM stock_posting WHERE action = 'PURCHASE_INVOICE' LIMIT 1")
    ).first():
        raise RuntimeError("archive retained goods purchase bill postings before downgrade")
    op.execute("""ALTER TABLE stock_posting
        DROP CHECK ck_stock_posting_stock_posting_action,
        ADD CONSTRAINT ck_stock_posting_stock_posting_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH',
            'TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','COUNT','REVERSAL'))""")
