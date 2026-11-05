"""Indexed platform directory: ix_tenant_created_id. One atomic DDL per revision."""

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tenant_created_id", "tenant", ["created_at","id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_created_id", table_name="tenant")
