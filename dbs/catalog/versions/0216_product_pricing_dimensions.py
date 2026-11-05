"""Typed pricing gates; legacy releases preserve their existing supported behaviour."""

from alembic import context, op
from sqlalchemy import text

revision = "0216"
down_revision = "0215"
branch_labels = None
depends_on = None

_ALTER = """
ALTER TABLE product_pricing_policy
    ADD COLUMN multiple_price_levels_mode VARCHAR(10) NOT NULL DEFAULT 'INHERIT',
    ADD CONSTRAINT ck_product_pricing_policy_pricing_multiple_price_levels_mode
        CHECK (multiple_price_levels_mode IN ('INHERIT','DISABLED','ENABLED')),
    ADD COLUMN unit_prices_mode VARCHAR(10) NOT NULL DEFAULT 'INHERIT',
    ADD CONSTRAINT ck_product_pricing_policy_pricing_unit_prices_mode
        CHECK (unit_prices_mode IN ('INHERIT','DISABLED','ENABLED')),
    ADD COLUMN quantity_tiers_mode VARCHAR(10) NOT NULL DEFAULT 'INHERIT',
    ADD CONSTRAINT ck_product_pricing_policy_pricing_quantity_tiers_mode
        CHECK (quantity_tiers_mode IN ('INHERIT','DISABLED','ENABLED')),
    ADD COLUMN channel_prices_mode VARCHAR(10) NOT NULL DEFAULT 'INHERIT',
    ADD CONSTRAINT ck_product_pricing_policy_pricing_channel_prices_mode
        CHECK (channel_prices_mode IN ('INHERIT','DISABLED','ENABLED')),
    ADD COLUMN additional_currencies_mode VARCHAR(10) NOT NULL DEFAULT 'INHERIT',
    ADD CONSTRAINT ck_product_pricing_policy_pricing_additional_currencies_mode
        CHECK (additional_currencies_mode IN ('INHERIT','DISABLED','ENABLED')),
    ADD COLUMN formula_prices_mode VARCHAR(10) NOT NULL DEFAULT 'INHERIT',
    ADD CONSTRAINT ck_product_pricing_policy_pricing_formula_prices_mode
        CHECK (formula_prices_mode IN ('INHERIT','DISABLED','ENABLED'))
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "pricing-dimension rollback requires online validation of history"
        )
    authored = (
        op.get_bind()
        .execute(
            text("""
        SELECT 1 FROM product_pricing_policy
        WHERE multiple_price_levels_mode <> 'INHERIT'
           OR unit_prices_mode <> 'INHERIT'
           OR quantity_tiers_mode <> 'INHERIT'
           OR channel_prices_mode <> 'INHERIT'
           OR additional_currencies_mode <> 'INHERIT'
           OR formula_prices_mode <> 'INHERIT'
        LIMIT 1
    """)
        )
        .first()
    )
    if authored is not None:
        raise RuntimeError("cannot discard authored pricing-dimension settings")
    op.execute("""
ALTER TABLE product_pricing_policy
    DROP CHECK ck_product_pricing_policy_pricing_multiple_price_levels_mode,
    DROP COLUMN multiple_price_levels_mode,
    DROP CHECK ck_product_pricing_policy_pricing_unit_prices_mode,
    DROP COLUMN unit_prices_mode,
    DROP CHECK ck_product_pricing_policy_pricing_quantity_tiers_mode,
    DROP COLUMN quantity_tiers_mode,
    DROP CHECK ck_product_pricing_policy_pricing_channel_prices_mode,
    DROP COLUMN channel_prices_mode,
    DROP CHECK ck_product_pricing_policy_pricing_additional_currencies_mode,
    DROP COLUMN additional_currencies_mode,
    DROP CHECK ck_product_pricing_policy_pricing_formula_prices_mode,
    DROP COLUMN formula_prices_mode
""")
