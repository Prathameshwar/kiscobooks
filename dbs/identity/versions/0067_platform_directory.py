"""Indexed platform directory: ix_tenant_name_id. One atomic DDL per revision."""

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tenant_name_id", "tenant", ["name","id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_name_id", table_name="tenant")
