"""Index supplier bill numbers for duplicate detection; one DDL statement."""

from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_voucher_invoice_supplier_number",
        "voucher_invoice_detail",
        ["tenant_id", "company_id", "supplier_invoice_number"],
    )


def downgrade() -> None:
    # No foreign key relies on this index; the scope unique key still serves the revision FK.
    op.drop_index("ix_voucher_invoice_supplier_number", table_name="voucher_invoice_detail")
