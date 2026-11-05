"""Create invoice_template_component; reusable blocks composed into layouts."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE invoice_template_component (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,
    component_category VARCHAR(32) NOT NULL,
    description VARCHAR(500) NULL,
    content_definition JSON NOT NULL,
    is_system BOOL NOT NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_invoice_template_component PRIMARY KEY (id),
    CONSTRAINT uq_invoice_template_component_code UNIQUE (tenant_id, company_id, code),
    KEY ix_invoice_template_component_company (tenant_id, company_id),
    KEY ix_invoice_template_component_lookup (tenant_id, company_id, is_active, component_category),
    KEY ix_invoice_template_component_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_template_component")
