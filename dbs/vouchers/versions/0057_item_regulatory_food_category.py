"""Project reviewed Catalog food category."""

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE voucher_item_regulatory_projection "
    "ADD COLUMN food_category_code VARCHAR(30) NULL"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE voucher_item_regulatory_projection DROP COLUMN food_category_code")
