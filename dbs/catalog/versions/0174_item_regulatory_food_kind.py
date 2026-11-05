"""Permit food as a distinct regulatory product kind."""

from alembic import op

revision = "0174"
down_revision = "0173"
branch_labels = None
depends_on = None

_ALTER = """ALTER TABLE item_regulatory_classification
    DROP CHECK ck_item_regulatory_kind,
    ADD CONSTRAINT ck_item_regulatory_kind
        CHECK (product_kind IN ('NON_DRUG','MEDICINE','FOOD'))"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("""ALTER TABLE item_regulatory_classification
        DROP CHECK ck_item_regulatory_kind,
        ADD CONSTRAINT ck_item_regulatory_kind
            CHECK (product_kind IN ('NON_DRUG','MEDICINE'))""")
