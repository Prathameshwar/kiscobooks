"""Create routing_rule; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE routing_rule (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    event_key VARCHAR(120) NOT NULL,
    category VARCHAR(30) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    provider_account_id BINARY(16) NOT NULL,
    sender_identity_id BINARY(16) NOT NULL,
    priority SMALLINT UNSIGNED NOT NULL,
    weight SMALLINT UNSIGNED NOT NULL,
    max_attempts SMALLINT UNSIGNED NOT NULL,
    timeout_seconds SMALLINT UNSIGNED NOT NULL,
    initial_backoff_seconds INT UNSIGNED NOT NULL,
    max_backoff_seconds INT UNSIGNED NOT NULL,
    conditions JSON NULL,
    is_active TINYINT(1) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT pk_routing_rule PRIMARY KEY (id),
    CONSTRAINT uq_routing_rule_resolution_priority UNIQUE (tenant_id, company_id, event_key, category, channel, priority),
    CONSTRAINT fk_routing_rule_provider_account_id FOREIGN KEY (provider_account_id) REFERENCES provider_account (id),
    CONSTRAINT fk_routing_rule_sender_identity_id FOREIGN KEY (sender_identity_id) REFERENCES sender_identity (id),
    KEY ix_routing_rule_tenant_id (tenant_id),
    KEY ix_routing_rule_active_resolution (tenant_id, company_id, event_key, category, channel, is_active, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE routing_rule")

