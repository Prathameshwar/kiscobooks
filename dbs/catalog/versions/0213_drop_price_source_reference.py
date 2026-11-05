"""Remove the retired published price note; old text needs backup recovery."""

from alembic import op

revision = "0213"
down_revision = "0212"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE item_price DROP COLUMN source_reference"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    # Restore compatibility with old writers; deleted notes cannot be reconstructed.
    op.execute(
        "ALTER TABLE item_price ADD COLUMN source_reference VARCHAR(500) NOT NULL DEFAULT ''"
    )
