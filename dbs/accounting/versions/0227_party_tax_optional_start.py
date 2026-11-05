"""Allow a party tax registration with no lower date bound; one atomic DDL."""

from alembic import op
from sqlalchemy import text

revision = "0227"
down_revision = "0226"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE party_tax_registration MODIFY COLUMN valid_from DATE NULL")


def downgrade() -> None:
    # Never invent historical start dates to satisfy the old contract.
    if op.get_bind().execute(
        text("SELECT id FROM party_tax_registration WHERE valid_from IS NULL LIMIT 1")
    ).first():
        raise RuntimeError("supply reviewed tax registration start dates before downgrade")
    op.execute("ALTER TABLE party_tax_registration MODIFY COLUMN valid_from DATE NOT NULL")
