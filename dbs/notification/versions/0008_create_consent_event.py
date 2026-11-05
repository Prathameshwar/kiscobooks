"""Create consent_event; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE consent_event (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    recipient_endpoint_id BINARY(16) NOT NULL,
    purpose VARCHAR(30) NOT NULL,
    state VARCHAR(20) NOT NULL,
    source VARCHAR(40) NOT NULL,
    source_event_key VARCHAR(255) NOT NULL,
    actor_user_id BINARY(16) NULL,
    evidence_ref VARCHAR(500) NULL,
    occurred_at DATETIME(6) NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    metadata JSON NULL,
    CONSTRAINT pk_consent_event PRIMARY KEY (id),
    CONSTRAINT uq_consent_event_source_key UNIQUE (tenant_id, source, source_event_key),
    CONSTRAINT fk_consent_event_recipient_endpoint_id FOREIGN KEY (recipient_endpoint_id) REFERENCES recipient_endpoint (id),
    KEY ix_consent_event_tenant_id (tenant_id),
    KEY ix_consent_event_endpoint_purpose_time (recipient_endpoint_id, purpose, occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE consent_event")

