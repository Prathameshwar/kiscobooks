"""enforce notification delivery space. One DDL statement per revision."""
from alembic import op
revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_delivery MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_notification_delivery_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_delivery MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_notification_delivery_space_owner
""")
