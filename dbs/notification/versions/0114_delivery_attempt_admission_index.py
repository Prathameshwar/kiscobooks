"""Bound admission queries by owner, provider and time."""
from alembic import op

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE delivery_attempt
        ADD INDEX ix_delivery_attempt_capacity (tenant_id, space_id, started_at, provider_account_id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE delivery_attempt DROP INDEX ix_delivery_attempt_capacity")
