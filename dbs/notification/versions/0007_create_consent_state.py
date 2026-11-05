"""Create consent_state; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE consent_state (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    recipient_endpoint_id BINARY(16) NOT NULL,
    purpose VARCHAR(30) NOT NULL,
    state VARCHAR(20) NOT NULL,
    lawful_basis VARCHAR(40) NULL,
    evidence_ref VARCHAR(500) NULL,
    effective_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NULL,
    last_event_id BINARY(16) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_consent_state PRIMARY KEY (id),
    CONSTRAINT uq_consent_state_endpoint_purpose UNIQUE (recipient_endpoint_id, purpose),
    CONSTRAINT fk_consent_state_recipient_endpoint_id FOREIGN KEY (recipient_endpoint_id) REFERENCES recipient_endpoint (id),
    KEY ix_consent_state_tenant_id (tenant_id),
    KEY ix_consent_state_tenant_state_expires (tenant_id, state, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE consent_state")

