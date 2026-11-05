"""Indexed platform directory: ix_tenant_status_slug_id. One atomic DDL per revision."""

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tenant_status_slug_id", "tenant", ["status","slug","id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_status_slug_id", table_name="tenant")
