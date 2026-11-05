"""Retained view and execution policy; one atomic additive column statement."""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("report_job", sa.Column("options", sa.JSON(), nullable=True))


def downgrade():
    # Disposable rehearsal only; production rollback preserves retained contracts.
    op.drop_column("report_job", "options")
