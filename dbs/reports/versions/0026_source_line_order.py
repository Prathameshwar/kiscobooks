"""Journal-local keyset order; one index DDL statement."""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_report_fact_version_line_order ON report_fact_version "
               "(tenant_id, company_id, epoch_id, entity, relation_id, line_sequence, source_id, valid_from_sequence)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_report_fact_version_line_order ON report_fact_version")
