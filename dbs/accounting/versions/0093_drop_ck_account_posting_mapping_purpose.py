"""drop the posting purpose check before widening it; one DDL statement per direction."""
from alembic import op

revision = '0093'
down_revision = '0092'
branch_labels = None
depends_on = None

# Downgrade restores the original purposes; it fails while CESS/RCM/TDS/TCS mappings exist.

UPGRADE = 'ALTER TABLE account_posting_mapping DROP CHECK ck_account_posting_mapping_account_posting_mapping_purpose'
DOWNGRADE = "ALTER TABLE account_posting_mapping ADD CONSTRAINT ck_account_posting_mapping_account_posting_mapping_purpose CHECK (purpose IN ('SALES_REVENUE', 'SERVICE_REVENUE', 'SALES_RETURN', 'PURCHASE_EXPENSE', 'OUTPUT_CGST', 'OUTPUT_SGST', 'OUTPUT_UTGST', 'OUTPUT_IGST', 'INPUT_CGST', 'INPUT_SGST', 'INPUT_UTGST', 'INPUT_IGST', 'CASH_RECEIPT', 'BANK_RECEIPT', 'INVENTORY_VALUE', 'COST_OF_GOODS', 'ROUNDING_GAIN', 'ROUNDING_LOSS'))"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
