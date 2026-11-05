"""Remove the retired price draft note; old text needs backup recovery."""

from alembic import op

revision = "0212"
down_revision = "0211"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE item_price_draft DROP COLUMN source_reference"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    # Restore compatibility with old writers; deleted notes cannot be reconstructed.
    op.execute(
        "ALTER TABLE item_price_draft ADD COLUMN source_reference VARCHAR(500) NOT NULL DEFAULT ''"
    )
