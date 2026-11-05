"""Index routing_rule keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE routing_rule ADD KEY ix_routing_rule_scoped_list_1 (`tenant_id`,
    `space_id`,
    `created_at`,
    `id`),
    ADD KEY ix_routing_rule_scoped_list_2 (`tenant_id`,
    `space_id`,
    `priority`,
    `id`),
    ADD KEY ix_routing_rule_scoped_list_3 (`tenant_id`,
    `space_id`,
    `channel`,
    `company_id`,
    `event_key`,
    `category`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE routing_rule DROP INDEX ix_routing_rule_scoped_list_1,
    DROP INDEX ix_routing_rule_scoped_list_2,
    DROP INDEX ix_routing_rule_scoped_list_3
""")
