"""Create the owner-version checkpoint for party destinations."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE party_endpoint_checkpoint (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    party_id BINARY(16) NOT NULL,
    purpose VARCHAR(20) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    source_version BIGINT NOT NULL,
    endpoint_id BINARY(16) NULL,
    CONSTRAINT pk_party_endpoint_checkpoint PRIMARY KEY (id),
    CONSTRAINT uq_party_endpoint_checkpoint_source UNIQUE
        (tenant_id, company_id, party_id, purpose, channel),
    KEY ix_party_endpoint_checkpoint_party (tenant_id, company_id, party_id),
    KEY ix_party_endpoint_checkpoint_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE party_endpoint_checkpoint")
