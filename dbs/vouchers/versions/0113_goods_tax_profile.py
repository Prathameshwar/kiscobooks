"""B24: forward-charge GST on purchased goods; one atomic ALTER."""

from alembic import op
from sqlalchemy import text

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE voucher_supply_tax_context
        DROP CHECK ck_voucher_supply_tax_context_profile,
        ADD CONSTRAINT ck_voucher_supply_tax_context_profile CHECK (
            profile IN ('UNTAXED_ACCOUNT','INDIA_DOMESTIC_SERVICE','INDIA_DOMESTIC_SERVICE_RCM',
            'INDIA_DOMESTIC_GOODS'))""")


def downgrade() -> None:
    if op.get_bind().execute(
        text("SELECT id FROM voucher_supply_tax_context WHERE profile = 'INDIA_DOMESTIC_GOODS' LIMIT 1")
    ).first():
        raise RuntimeError("archive retained goods GST contexts before downgrade")
    op.execute("""ALTER TABLE voucher_supply_tax_context
        DROP CHECK ck_voucher_supply_tax_context_profile,
        ADD CONSTRAINT ck_voucher_supply_tax_context_profile CHECK (
            profile IN ('UNTAXED_ACCOUNT','INDIA_DOMESTIC_SERVICE','INDIA_DOMESTIC_SERVICE_RCM'))""")
