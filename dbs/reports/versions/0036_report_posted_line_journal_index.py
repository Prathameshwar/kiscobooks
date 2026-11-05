"""Scoped journal drilldowns; one atomic additive index statement."""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_report_posted_line_journal",
        "report_posted_line",
        ["tenant_id", "company_id", "epoch_id", "journal_id", "posting_date",
         "line_sequence", "line_id", "valid_from_sequence"],
    )


def downgrade():
    op.drop_index("ix_report_posted_line_journal", table_name="report_posted_line")
