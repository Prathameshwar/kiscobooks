"""add CESS, reverse-charge and withholding posting purposes; one DDL statement per direction."""
from alembic import op

revision = '0094'
down_revision = '0093'
branch_labels = None
depends_on = None

UPGRADE = "ALTER TABLE account_posting_mapping ADD CONSTRAINT ck_account_posting_mapping_account_posting_mapping_purpose CHECK (purpose IN ('SALES_REVENUE', 'SERVICE_REVENUE', 'SALES_RETURN', 'PURCHASE_EXPENSE', 'OUTPUT_CGST', 'OUTPUT_SGST', 'OUTPUT_UTGST', 'OUTPUT_IGST', 'OUTPUT_CESS', 'INPUT_CGST', 'INPUT_SGST', 'INPUT_UTGST', 'INPUT_IGST', 'INPUT_CESS', 'RCM_CGST', 'RCM_SGST', 'RCM_UTGST', 'RCM_IGST', 'RCM_CESS', 'TDS_PAYABLE', 'TCS_PAYABLE', 'TDS_RECEIVABLE', 'TCS_RECEIVABLE', 'CASH_RECEIPT', 'BANK_RECEIPT', 'INVENTORY_VALUE', 'COST_OF_GOODS', 'ROUNDING_GAIN', 'ROUNDING_LOSS'))"
DOWNGRADE = 'ALTER TABLE account_posting_mapping DROP CHECK ck_account_posting_mapping_account_posting_mapping_purpose'


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
