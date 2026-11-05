"""Index notification_delivery keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_delivery ADD KEY ix_notification_delivery_scoped_list_1 (`tenant_id`,
    `space_id`,
    `created_at`,
    `id`),
    ADD KEY ix_notification_delivery_scoped_list_2 (`tenant_id`,
    `space_id`,
    `status`,
    `created_at`,
    `id`),
    ADD KEY ix_notification_delivery_scoped_list_3 (`tenant_id`,
    `space_id`,
    `channel`,
    `created_at`,
    `id`),
    ADD KEY ix_notification_delivery_scoped_list_4 (`tenant_id`,
    `space_id`,
    `request_id`,
    `created_at`,
    `id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_delivery DROP INDEX ix_notification_delivery_scoped_list_1,
    DROP INDEX ix_notification_delivery_scoped_list_2,
    DROP INDEX ix_notification_delivery_scoped_list_3,
    DROP INDEX ix_notification_delivery_scoped_list_4
""")
