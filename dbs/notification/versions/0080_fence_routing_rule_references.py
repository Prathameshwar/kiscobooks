"""fence routing rule references. One DDL statement per revision."""
from alembic import op
revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE routing_rule ADD CONSTRAINT fk_routing_rule_provider_account_id_space FOREIGN KEY(provider_account_id,
    tenant_id,
    space_id) REFERENCES provider_account (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_routing_rule_sender_identity_id_space FOREIGN KEY(sender_identity_id,
    tenant_id,
    space_id) REFERENCES sender_identity (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE routing_rule DROP FOREIGN KEY fk_routing_rule_provider_account_id_space,
    DROP FOREIGN KEY fk_routing_rule_sender_identity_id_space
""")
