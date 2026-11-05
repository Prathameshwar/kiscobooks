"""Remove the retired product tax assignment note; old text needs backup recovery."""

from alembic import op

revision = "0211"
down_revision = "0210"
branch_labels = None
depends_on = None

_ALTER = "ALTER TABLE catalog_tax_binding DROP COLUMN source_reference"


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    # Restore compatibility with old writers; deleted notes cannot be reconstructed.
    op.execute(
        "ALTER TABLE catalog_tax_binding ADD COLUMN source_reference "
        "VARCHAR(500) NOT NULL DEFAULT ''"
    )
