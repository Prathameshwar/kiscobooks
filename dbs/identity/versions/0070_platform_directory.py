"""Indexed platform directory: ix_tenant_status_created_id. One atomic DDL per revision."""

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tenant_status_created_id", "tenant", ["status","created_at","id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_status_created_id", table_name="tenant")
