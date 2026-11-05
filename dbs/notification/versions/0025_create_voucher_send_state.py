"""Create voucher terminal-state fence for pending notification delivery."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE voucher_send_state (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    voucher_id BINARY(16) NOT NULL,
    source_version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT pk_voucher_send_state PRIMARY KEY (id),
    CONSTRAINT uq_voucher_send_state_source UNIQUE (tenant_id, company_id, voucher_id),
    KEY ix_voucher_send_state_voucher (tenant_id, company_id, voucher_id),
    KEY ix_voucher_send_state_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE voucher_send_state")
