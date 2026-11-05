"""fence delivery attempt references. One DDL statement per revision."""
from alembic import op
revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attempt ADD CONSTRAINT fk_delivery_attempt_provider_account_id_space FOREIGN KEY(provider_account_id,
    tenant_id,
    space_id) REFERENCES provider_account (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_delivery_attempt_sender_identity_id_space FOREIGN KEY(sender_identity_id,
    tenant_id,
    space_id) REFERENCES sender_identity (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_delivery_attempt_delivery_id_space FOREIGN KEY(delivery_id,
    tenant_id,
    space_id) REFERENCES notification_delivery (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attempt DROP FOREIGN KEY fk_delivery_attempt_provider_account_id_space,
    DROP FOREIGN KEY fk_delivery_attempt_sender_identity_id_space,
    DROP FOREIGN KEY fk_delivery_attempt_delivery_id_space
""")
