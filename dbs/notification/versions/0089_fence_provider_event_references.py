"""fence provider event references. One DDL statement per revision."""
from alembic import op
revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE provider_event ADD CONSTRAINT fk_provider_event_provider_account_id_space FOREIGN KEY(provider_account_id,
    tenant_id,
    space_id) REFERENCES provider_account (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_provider_event_delivery_id_space FOREIGN KEY(delivery_id,
    tenant_id,
    space_id) REFERENCES notification_delivery (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE provider_event DROP FOREIGN KEY fk_provider_event_provider_account_id_space,
    DROP FOREIGN KEY fk_provider_event_delivery_id_space
""")
