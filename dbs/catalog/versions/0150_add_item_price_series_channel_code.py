"""Add nullable ``channel_code`` to ``item_price_series`` bound to sales_channel; one DDL.

Nullable because a company without channel-scoped pricing keeps existing rows
untouched. The composite FK carries ``(tenant_id, company_id, channel_code)``
against ``sales_channel(tenant_id, company_id, code)`` — MySQL treats a NULL
member as unconstrained, so a null ``channel_code`` remains valid.
"""

from alembic import op

revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE item_price_series "
    "ADD COLUMN channel_code VARCHAR(30) NULL, "
    "ADD CONSTRAINT fk_item_price_series_channel "
    "FOREIGN KEY (tenant_id, company_id, channel_code) "
    "REFERENCES sales_channel (tenant_id, company_id, code), "
    "ADD INDEX ix_item_price_series_channel (tenant_id, company_id, channel_code)"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE item_price_series "
        "DROP FOREIGN KEY fk_item_price_series_channel, "
        "DROP INDEX ix_item_price_series_channel, "
        "DROP COLUMN channel_code"
    )
