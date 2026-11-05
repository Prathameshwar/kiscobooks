"""Record the owner's accepted payable total alongside its calculation hash; one atomic ALTER."""

from alembic import op

revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_invoice_detail "
        "ADD COLUMN payable_total DECIMAL(19,4) NULL, "
        "ADD CONSTRAINT ck_voucher_invoice_detail_voucher_invoice_payable_total "
        "CHECK (payable_total IS NULL OR payable_total >= 0)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_invoice_detail "
        "DROP CHECK ck_voucher_invoice_detail_voucher_invoice_payable_total, "
        "DROP COLUMN payable_total"
    )
