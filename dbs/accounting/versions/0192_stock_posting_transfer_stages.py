"""Explicit shipment/receipt transfer actions; one atomic ALTER."""
from alembic import op

revision = "0192"
down_revision = "0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE stock_posting
        DROP CHECK ck_stock_posting_stock_posting_action,
        ADD CONSTRAINT ck_stock_posting_stock_posting_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','TRANSFER_DISPATCH','TRANSFER_RECEIPT','CUSTOMER_RETURN','SUPPLIER_RETURN','REVERSAL')
        )""")


def downgrade() -> None:
    op.execute("""ALTER TABLE stock_posting
        DROP CHECK ck_stock_posting_stock_posting_action,
        ADD CONSTRAINT ck_stock_posting_stock_posting_action CHECK (
            action IN ('OPENING','RECEIPT','DISPATCH','TRANSFER','CUSTOMER_RETURN','SUPPLIER_RETURN','REVERSAL')
        )""")
