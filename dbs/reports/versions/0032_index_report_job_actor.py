"""Bounded actor-owned run/export history; one atomic index statement."""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_report_job_actor", "report_job",
                    ["tenant_id", "company_id", "actor_id", "kind", "id"])


def downgrade():
    op.drop_index("ix_report_job_actor", table_name="report_job")
