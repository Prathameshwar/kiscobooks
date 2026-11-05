"""Pin the approved owner calculation; one atomic ALTER."""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_invoice_detail ADD COLUMN accepted_calculation_hash VARCHAR(64) NULL, ADD CONSTRAINT ck_voucher_invoice_detail_calculation_hash CHECK (accepted_calculation_hash IS NULL OR LENGTH(accepted_calculation_hash) = 64)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_invoice_detail DROP CHECK ck_voucher_invoice_detail_calculation_hash, DROP COLUMN accepted_calculation_hash"
    )
