"""Stock snapshots avoid scanning financial facts or movement history for balance reports."""
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_report_fact_inventory_grain", "report_fact_version", [
        "tenant_id", "company_id", "epoch_id", "entity", "inventory_kind", "source_id",
        "valid_from_sequence",
    ])


def downgrade():
    op.drop_index("ix_report_fact_inventory_grain", table_name="report_fact_version")
