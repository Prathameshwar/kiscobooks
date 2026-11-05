"""Bounded registration-period scans; one reversible index DDL."""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_report_fact_version_gst_period ON report_fact_version "
               "(tenant_id,company_id,epoch_id,entity,relation_id,posting_date,source_id,valid_from_sequence)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_report_fact_version_gst_period ON report_fact_version")
