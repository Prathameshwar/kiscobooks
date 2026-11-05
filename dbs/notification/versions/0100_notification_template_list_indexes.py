"""Index notification_template keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_template ADD KEY ix_notification_template_scoped_list_1 (`tenant_id`,
    `space_id`,
    `created_at`,
    `id`),
    ADD KEY ix_notification_template_scoped_list_2 (`tenant_id`,
    `space_id`,
    `key`,
    `id`),
    ADD KEY ix_notification_template_scoped_list_3 (`tenant_id`,
    `space_id`,
    `event_key`,
    `company_id`,
    `is_active`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_template DROP INDEX ix_notification_template_scoped_list_1,
    DROP INDEX ix_notification_template_scoped_list_2,
    DROP INDEX ix_notification_template_scoped_list_3
""")
