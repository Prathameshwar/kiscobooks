"""Create invoice_template; `live_code` gives MySQL a partial unique key over live rows."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE invoice_template (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,
    description VARCHAR(500) NULL,
    paper_size VARCHAR(32) NOT NULL,
    page_orientation VARCHAR(16) NOT NULL,
    page_width_mm DECIMAL(19, 4) NULL,
    page_height_mm DECIMAL(19, 4) NULL,
    unit_of_measure VARCHAR(8) NOT NULL,
    status VARCHAR(20) NOT NULL,
    is_system BOOL NOT NULL,
    current_version_id BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    live_code VARCHAR(50) GENERATED ALWAYS AS (CASE WHEN status <> 'ARCHIVED' THEN code ELSE NULL END) STORED,
    CONSTRAINT pk_invoice_template PRIMARY KEY (id),
    CONSTRAINT uq_invoice_template_live_code UNIQUE (tenant_id, company_id, live_code),
    KEY ix_invoice_template_company (tenant_id, company_id),
    KEY ix_invoice_template_lookup (tenant_id, company_id, status, created_at),
    KEY ix_invoice_template_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_template")
