"""Require a food category on projected food classifications."""

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

_ALTER = """ALTER TABLE voucher_item_regulatory_projection
    DROP CHECK ck_voucher_item_reg_class_shape,
    ADD CONSTRAINT ck_voucher_item_reg_class_shape CHECK (
        (product_kind = 'NON_DRUG' AND licence_class IS NULL
            AND prescription_schedule IS NULL AND food_category_code IS NULL)
        OR (product_kind = 'FOOD' AND licence_class IS NULL
            AND prescription_schedule IS NULL AND food_category_code IS NOT NULL)
        OR (product_kind = 'MEDICINE' AND licence_class IN
            ('OTHER_THAN_C_C1_X','C_C1_EXCLUDING_X','SCHEDULE_X')
            AND prescription_schedule IN ('NONE','H','H1','X')
            AND food_category_code IS NULL))"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("""ALTER TABLE voucher_item_regulatory_projection
        DROP CHECK ck_voucher_item_reg_class_shape,
        ADD CONSTRAINT ck_voucher_item_reg_class_shape CHECK (
            (product_kind = 'NON_DRUG' AND licence_class IS NULL
                AND prescription_schedule IS NULL)
            OR (product_kind = 'MEDICINE' AND licence_class IN
                ('OTHER_THAN_C_C1_X','C_C1_EXCLUDING_X','SCHEDULE_X')
                AND prescription_schedule IN ('NONE','H','H1','X')))""")
