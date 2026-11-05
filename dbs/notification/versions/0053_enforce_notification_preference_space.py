"""enforce notification preference space. One DDL statement per revision."""
from alembic import op
revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_preference MODIFY COLUMN space_id BINARY(16) NOT NULL,
    DROP INDEX uq_notification_preference_subject_event_channel,
    ADD CONSTRAINT uq_notification_preference_subject_event_channel UNIQUE (`tenant_id`,
    `space_id`,
    `subject_type`,
    `subject_id`,
    `event_key`,
    `channel`),
    ADD CONSTRAINT uq_notification_preference_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_preference MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_notification_preference_subject_event_channel,
    ADD CONSTRAINT uq_notification_preference_subject_event_channel UNIQUE (`tenant_id`,
    `subject_type`,
    `subject_id`,
    `event_key`,
    `channel`),
    DROP INDEX uq_notification_preference_space_owner
""")
