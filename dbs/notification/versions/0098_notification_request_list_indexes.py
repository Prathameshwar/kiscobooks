"""Index notification_request keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_request ADD KEY ix_notification_request_scoped_list_1 (`tenant_id`,
    `space_id`,
    `received_at`,
    `id`),
    ADD KEY ix_notification_request_scoped_list_2 (`tenant_id`,
    `space_id`,
    `status`,
    `received_at`,
    `id`),
    ADD KEY ix_notification_request_scoped_list_3 (`tenant_id`,
    `space_id`,
    `event_key`,
    `received_at`,
    `id`),
    ADD KEY ix_notification_request_scoped_list_4 (`tenant_id`,
    `space_id`,
    `company_id`,
    `aggregate_id`,
    `received_at`,
    `id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_request DROP INDEX ix_notification_request_scoped_list_1,
    DROP INDEX ix_notification_request_scoped_list_2,
    DROP INDEX ix_notification_request_scoped_list_3,
    DROP INDEX ix_notification_request_scoped_list_4
""")
