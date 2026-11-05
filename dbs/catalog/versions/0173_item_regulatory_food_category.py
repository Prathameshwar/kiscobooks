"""Add the reviewed food category to dated item classification."""

from alembic import op

revision = "0173"
down_revision = "0172"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE item_regulatory_classification ADD COLUMN food_category_code VARCHAR(30) NULL"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute("ALTER TABLE item_regulatory_classification DROP COLUMN food_category_code")
