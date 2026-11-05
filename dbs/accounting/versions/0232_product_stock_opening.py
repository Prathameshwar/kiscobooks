"""Independent first openings for new products retain the company cutover."""

from alembic import context, op
from sqlalchemy import text

revision = "0232"
down_revision = "0231"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE stock_opening_control
    DROP INDEX uq_stock_opening_company,
    ADD COLUMN item_id BINARY(16) NULL,
    ADD COLUMN company_slot INTEGER NULL DEFAULT 1,
    ADD CONSTRAINT uq_stock_opening_company UNIQUE (tenant_id, company_id, company_slot),
    ADD CONSTRAINT uq_stock_opening_product UNIQUE (tenant_id, company_id, item_id),
    ADD CONSTRAINT ck_stock_opening_control_stock_opening_owner CHECK (
        (item_id IS NULL AND company_slot IS NOT NULL AND company_slot = 1) OR
        (item_id IS NOT NULL AND company_slot IS NULL))
""")


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("product-opening rollback requires retained-history validation")
    if op.get_bind().execute(text(
        "SELECT 1 FROM stock_opening_control WHERE item_id IS NOT NULL LIMIT 1"
    )).first() is not None:
        raise RuntimeError("cannot discard retained product opening evidence")
    op.execute("""
ALTER TABLE stock_opening_control
    DROP CHECK ck_stock_opening_control_stock_opening_owner,
    DROP INDEX uq_stock_opening_product,
    DROP INDEX uq_stock_opening_company,
    DROP COLUMN company_slot,
    DROP COLUMN item_id,
    ADD CONSTRAINT uq_stock_opening_company UNIQUE (tenant_id, company_id)
""")
