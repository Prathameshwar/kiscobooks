"""Allow one generic and one price series per channel for each SKU/plan/pack."""

from alembic import op

revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE item_price_series "
    "ADD COLUMN channel_scope_key VARCHAR(30) "
    "GENERATED ALWAYS AS (COALESCE(channel_code, '*')) STORED NOT NULL, "
    "DROP INDEX uq_v88_1, "
    "ADD UNIQUE KEY uq_v88_1 "
    "(tenant_id, company_id, plan_id, price_scope_id, unit_revision_id, channel_scope_key)"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE item_price_series "
        "DROP INDEX uq_v88_1, "
        "DROP COLUMN channel_scope_key, "
        "ADD UNIQUE KEY uq_v88_1 "
        "(tenant_id, company_id, plan_id, price_scope_id, unit_revision_id)"
    )
