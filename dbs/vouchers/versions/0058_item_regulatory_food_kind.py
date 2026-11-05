"""Permit food as a distinct projected product kind."""

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

_ALTER = """ALTER TABLE voucher_item_regulatory_projection
    DROP CHECK ck_voucher_item_reg_kind,
    ADD CONSTRAINT ck_voucher_item_reg_kind
        CHECK (product_kind IN ('NON_DRUG','MEDICINE','FOOD'))"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("""ALTER TABLE voucher_item_regulatory_projection
        DROP CHECK ck_voucher_item_reg_kind,
        ADD CONSTRAINT ck_voucher_item_reg_kind
            CHECK (product_kind IN ('NON_DRUG','MEDICINE'))""")
