"""Create notification_delivery; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE notification_delivery (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    request_id BINARY(16) NOT NULL,
    recipient_endpoint_id BINARY(16) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    destination_hmac BINARY(32) NOT NULL,
    destination_masked VARCHAR(320) NOT NULL,
    template_version_id BINARY(16) NOT NULL,
    provider_template_binding_id BINARY(16) NULL,
    provider_account_id BINARY(16) NOT NULL,
    sender_identity_id BINARY(16) NOT NULL,
    routing_rule_id BINARY(16) NOT NULL,
    status VARCHAR(20) NOT NULL,
    status_reason VARCHAR(120) NULL,
    attempt_count SMALLINT UNSIGNED NOT NULL,
    next_attempt_at DATETIME(6) NULL,
    accepted_at DATETIME(6) NULL,
    delivered_at DATETIME(6) NULL,
    read_at DATETIME(6) NULL,
    failed_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    provider_message_id VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_notification_delivery PRIMARY KEY (id),
    CONSTRAINT uq_notification_delivery_request_endpoint_channel UNIQUE (request_id, recipient_endpoint_id, channel),
    CONSTRAINT fk_notification_delivery_request_id FOREIGN KEY (request_id) REFERENCES notification_request (id),
    CONSTRAINT fk_notification_delivery_recipient_endpoint_id FOREIGN KEY (recipient_endpoint_id) REFERENCES recipient_endpoint (id),
    CONSTRAINT fk_notification_delivery_template_version_id FOREIGN KEY (template_version_id) REFERENCES template_version (id),
    CONSTRAINT fk_notification_delivery_provider_template_binding_id FOREIGN KEY (provider_template_binding_id) REFERENCES provider_template_binding (id),
    CONSTRAINT fk_notification_delivery_provider_account_id FOREIGN KEY (provider_account_id) REFERENCES provider_account (id),
    CONSTRAINT fk_notification_delivery_sender_identity_id FOREIGN KEY (sender_identity_id) REFERENCES sender_identity (id),
    CONSTRAINT fk_notification_delivery_routing_rule_id FOREIGN KEY (routing_rule_id) REFERENCES routing_rule (id),
    KEY ix_notification_delivery_tenant_id (tenant_id),
    KEY ix_notification_delivery_status_next (tenant_id, status, next_attempt_at),
    KEY ix_notification_delivery_provider_message (provider_account_id, provider_message_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE notification_delivery")

