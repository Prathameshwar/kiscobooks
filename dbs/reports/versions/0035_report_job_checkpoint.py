"""Bounded-unit recovery checkpoint; one atomic additive column statement."""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_job", sa.Column("checkpoint", sa.JSON(), nullable=True))


def downgrade():
    # Disposable rehearsal only; production rollback preserves partial evidence.
    op.drop_column("report_job", "checkpoint")
