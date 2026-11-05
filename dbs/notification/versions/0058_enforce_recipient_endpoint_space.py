"""enforce recipient endpoint space. One DDL statement per revision."""
from alembic import op
revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE recipient_endpoint MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_recipient_endpoint_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`),
    DROP INDEX uq_recipient_endpoint_subject_channel_destination,
    ADD CONSTRAINT uq_recipient_endpoint_subject_channel_destination UNIQUE (`tenant_id`,
    `space_id`,
    `subject_type`,
    `subject_id`,
    `company_id`,
    `channel`,
    `destination_hmac`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE recipient_endpoint MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_recipient_endpoint_space_owner,
    DROP INDEX uq_recipient_endpoint_subject_channel_destination,
    ADD CONSTRAINT uq_recipient_endpoint_subject_channel_destination UNIQUE (`tenant_id`,
    `subject_type`,
    `subject_id`,
    `company_id`,
    `channel`,
    `destination_hmac`)
""")
