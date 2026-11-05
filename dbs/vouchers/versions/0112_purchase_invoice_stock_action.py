"""B24: a Purchase bill that brings its goods into stock; one atomic ALTER."""

from alembic import op
from sqlalchemy import text

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE voucher_stock_context
        DROP CHECK ck_voucher_stock_context_voucher_stock_context_action,
        ADD CONSTRAINT ck_voucher_stock_context_voucher_stock_context_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH',
            'TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','COUNT','PURCHASE_INVOICE'))""")


def downgrade() -> None:
    if op.get_bind().execute(
        text("SELECT id FROM voucher_stock_context WHERE action = 'PURCHASE_INVOICE' LIMIT 1")
    ).first():
        raise RuntimeError("archive retained goods purchase bills before downgrade")
    op.execute("""ALTER TABLE voucher_stock_context
        DROP CHECK ck_voucher_stock_context_voucher_stock_context_action,
        ADD CONSTRAINT ck_voucher_stock_context_voucher_stock_context_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH',
            'TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','COUNT'))""")
