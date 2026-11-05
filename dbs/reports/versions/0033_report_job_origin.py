"""Immutable drilldown provenance; one atomic additive column statement."""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_job", sa.Column("origin", sa.JSON(), nullable=True))


def downgrade():
    # Only a disposable migration rehearsal may remove retained drilldown provenance.
    # Production rollback keeps the additive schema and pauses new admissions.
    op.drop_column("report_job", "origin")
