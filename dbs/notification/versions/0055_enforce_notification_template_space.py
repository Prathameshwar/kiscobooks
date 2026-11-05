"""enforce notification template space. One DDL statement per revision."""
from alembic import op
revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_template MODIFY COLUMN space_id BINARY(16) NOT NULL,
    DROP INDEX uq_notification_template_company_key,
    ADD CONSTRAINT uq_notification_template_company_key UNIQUE (`tenant_id`,
    `space_id`,
    `company_id`,
    `key`),
    ADD CONSTRAINT uq_notification_template_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_template MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_notification_template_company_key,
    ADD CONSTRAINT uq_notification_template_company_key UNIQUE (`tenant_id`,
    `company_id`,
    `key`),
    DROP INDEX uq_notification_template_space_owner
""")
