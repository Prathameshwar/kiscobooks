"""Bind posting reservations to their financial service; preserve Billing rows."""
from alembic import op
import sqlalchemy as sa

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE posting_reservation ADD COLUMN owner_service VARCHAR(20) NOT NULL DEFAULT 'billing'")


def downgrade() -> None:
    # Never discard a non-Billing owner when returning to the Billing-only contract.
    foreign_owner = op.get_bind().execute(sa.text(
        "SELECT 1 FROM posting_reservation WHERE owner_service <> 'billing' LIMIT 1"
    )).scalar()
    if foreign_owner is not None:
        raise RuntimeError("retain Accounting reservation ownership; downgrade is unsafe")
    op.execute("ALTER TABLE posting_reservation DROP COLUMN owner_service")
