"""Native component-specific pending-credit posting mappings; one ALTER."""

from alembic import op

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None

OLD = (
    "'SALES_REVENUE', 'SERVICE_REVENUE', 'SALES_RETURN', 'PURCHASE_EXPENSE', "
    "'OUTPUT_CGST', 'OUTPUT_SGST', 'OUTPUT_UTGST', 'OUTPUT_IGST', 'OUTPUT_CESS', "
    "'INPUT_CGST', 'INPUT_SGST', 'INPUT_UTGST', 'INPUT_IGST', 'INPUT_CESS', "
    "'RCM_CGST', 'RCM_SGST', 'RCM_UTGST', 'RCM_IGST', 'RCM_CESS', "
    "'TDS_PAYABLE', 'TCS_PAYABLE', 'TDS_RECEIVABLE', 'TCS_RECEIVABLE', "
    "'CASH_RECEIPT', 'BANK_RECEIPT', 'INVENTORY_VALUE', 'COST_OF_GOODS', 'ROUNDING_GAIN', 'ROUNDING_LOSS'"
)
NEW = OLD + ", 'PENDING_CGST', 'PENDING_SGST', 'PENDING_UTGST', 'PENDING_IGST', 'PENDING_CESS'"
NAME = "ck_account_posting_mapping_account_posting_mapping_purpose"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE account_posting_mapping DROP CHECK {NAME}, ADD CONSTRAINT {NAME} CHECK (purpose IN ({NEW}))"
    )


def downgrade() -> None:
    # Refuse if pending-credit mappings exist; never reinterpret existing postings.
    op.execute(
        f"ALTER TABLE account_posting_mapping DROP CHECK {NAME}, ADD CONSTRAINT {NAME} CHECK (purpose IN ({OLD}))"
    )
