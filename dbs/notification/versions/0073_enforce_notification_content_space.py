"""enforce notification content space. One DDL statement per revision."""
from alembic import op
revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_content MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_notification_content_space_owner UNIQUE (`delivery_id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_content MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_notification_content_space_owner
""")
