"""enforce routing rule space. One DDL statement per revision."""
from alembic import op
revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE routing_rule MODIFY COLUMN space_id BINARY(16) NOT NULL,
    ADD CONSTRAINT uq_routing_rule_space_owner UNIQUE (`id`,
    `tenant_id`,
    `space_id`),
    DROP INDEX uq_routing_rule_resolution_priority,
    ADD CONSTRAINT uq_routing_rule_resolution_priority UNIQUE (`tenant_id`,
    `space_id`,
    `company_id`,
    `event_key`,
    `category`,
    `channel`,
    `priority`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE routing_rule MODIFY COLUMN space_id BINARY(16) NULL,
    DROP INDEX uq_routing_rule_space_owner,
    DROP INDEX uq_routing_rule_resolution_priority,
    ADD CONSTRAINT uq_routing_rule_resolution_priority UNIQUE (`tenant_id`,
    `company_id`,
    `event_key`,
    `category`,
    `channel`,
    `priority`)
""")
