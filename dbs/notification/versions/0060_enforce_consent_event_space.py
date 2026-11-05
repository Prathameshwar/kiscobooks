"""enforce consent event space. One DDL statement per revision."""
from alembic import op
revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE consent_event MODIFY COLUMN space_id BINARY(16) NOT NULL,
    DROP INDEX uq_consent_event_source_key,
    ADD CONSTRAINT uq_consent_event_source_key UNIQUE (`tenant_id`,
    `space_id`,
    `source`,
    `source_event_key`),
    ADD CONSTRAINT uq_consent_event_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE consent_event MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_consent_event_source_key,
    ADD CONSTRAINT uq_consent_event_source_key UNIQUE (`tenant_id`,
    `source`,
    `source_event_key`),
    DROP INDEX uq_consent_event_space_owner
""")
