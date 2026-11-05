"""fence notification delivery references. One DDL statement per revision."""
from alembic import op
revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_delivery ADD CONSTRAINT fk_notification_delivery_request_id_space FOREIGN KEY(request_id,
    tenant_id,
    space_id) REFERENCES notification_request (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_notification_delivery_sender_identity_id_space FOREIGN KEY(sender_identity_id,
    tenant_id,
    space_id) REFERENCES sender_identity (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_notification_delivery_provider_template_binding_id_space FOREIGN KEY(provider_template_binding_id,
    tenant_id,
    space_id) REFERENCES provider_template_binding (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_notification_delivery_provider_account_id_space FOREIGN KEY(provider_account_id,
    tenant_id,
    space_id) REFERENCES provider_account (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_notification_delivery_recipient_endpoint_id_space FOREIGN KEY(recipient_endpoint_id,
    tenant_id,
    space_id) REFERENCES recipient_endpoint (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_notification_delivery_routing_rule_id_space FOREIGN KEY(routing_rule_id,
    tenant_id,
    space_id) REFERENCES routing_rule (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_notification_delivery_template_version_id_space FOREIGN KEY(template_version_id,
    tenant_id,
    space_id) REFERENCES template_version (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE notification_delivery DROP FOREIGN KEY fk_notification_delivery_request_id_space,
    DROP FOREIGN KEY fk_notification_delivery_sender_identity_id_space,
    DROP FOREIGN KEY fk_notification_delivery_provider_template_binding_id_space,
    DROP FOREIGN KEY fk_notification_delivery_provider_account_id_space,
    DROP FOREIGN KEY fk_notification_delivery_recipient_endpoint_id_space,
    DROP FOREIGN KEY fk_notification_delivery_routing_rule_id_space,
    DROP FOREIGN KEY fk_notification_delivery_template_version_id_space
""")
