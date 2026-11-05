"""enforce notification request space. One DDL statement per revision."""
from alembic import op
revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_request MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_notification_request_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_request MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_notification_request_space_owner
""")
