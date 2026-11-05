"""Inventory grain projection; one additive statement."""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_fact_version", sa.Column("inventory_kind", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("report_fact_version", "inventory_kind")
