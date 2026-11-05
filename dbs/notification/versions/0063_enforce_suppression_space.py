"""enforce suppression space. One DDL statement per revision."""
from alembic import op
revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE suppression MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_suppression_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`),
    DROP INDEX uq_suppression_source_key,
    ADD CONSTRAINT uq_suppression_source_key UNIQUE (`tenant_id`,
    `space_id`,
    `source`,
    `source_event_key`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE suppression MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_suppression_space_owner,
    DROP INDEX uq_suppression_source_key,
    ADD CONSTRAINT uq_suppression_source_key UNIQUE (`tenant_id`,
    `source`,
    `source_event_key`)
""")
