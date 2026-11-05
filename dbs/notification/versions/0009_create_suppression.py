"""Create suppression; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE suppression (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    recipient_endpoint_id BINARY(16) NULL,
    channel VARCHAR(20) NOT NULL,
    destination_hmac BINARY(32) NOT NULL,
    scope_type VARCHAR(20) NOT NULL,
    scope_key VARCHAR(120) NOT NULL,
    reason VARCHAR(40) NOT NULL,
    source VARCHAR(40) NOT NULL,
    source_event_key VARCHAR(255) NOT NULL,
    valid_from DATETIME(6) NOT NULL,
    valid_to DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    CONSTRAINT pk_suppression PRIMARY KEY (id),
    CONSTRAINT uq_suppression_source_key UNIQUE (tenant_id, source, source_event_key),
    CONSTRAINT fk_suppression_recipient_endpoint_id FOREIGN KEY (recipient_endpoint_id) REFERENCES recipient_endpoint (id),
    KEY ix_suppression_tenant_id (tenant_id),
    KEY ix_suppression_resolution (tenant_id, channel, destination_hmac, valid_from, valid_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE suppression")

