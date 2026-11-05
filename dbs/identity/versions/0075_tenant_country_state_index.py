"""Explicit supporting index for the tenant's regional pair."""

from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_tenant_default_country_state "
        "ON tenant (default_country_code, default_state_code)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_tenant_default_country_state ON tenant")
