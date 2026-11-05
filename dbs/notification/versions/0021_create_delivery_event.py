"""Create delivery_event; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE delivery_event (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    delivery_id BINARY(16) NOT NULL,
    source VARCHAR(40) NOT NULL,
    source_event_key VARCHAR(255) NOT NULL,
    from_status VARCHAR(20) NULL,
    to_status VARCHAR(20) NOT NULL,
    reason_code VARCHAR(120) NULL,
    provider_occurred_at DATETIME(6) NULL,
    observed_at DATETIME(6) NOT NULL,
    metadata JSON NULL,
    CONSTRAINT pk_delivery_event PRIMARY KEY (id),
    CONSTRAINT uq_delivery_event_source_key UNIQUE (source, source_event_key),
    CONSTRAINT fk_delivery_event_delivery_id FOREIGN KEY (delivery_id) REFERENCES notification_delivery (id),
    KEY ix_delivery_event_tenant_id (tenant_id),
    KEY ix_delivery_event_timeline (tenant_id, delivery_id, observed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE delivery_event")

