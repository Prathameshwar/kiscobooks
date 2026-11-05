"""Create invoice_template_assignment; which layout a document kind prints on."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE invoice_template_assignment (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    voucher_kind VARCHAR(50) NOT NULL,
    voucher_type_id BINARY(16) NULL,
    branch_id BINARY(16) NULL,
    currency_code VARCHAR(3) NULL,
    customer_tax_category VARCHAR(32) NULL,
    template_id BINARY(16) NOT NULL,
    specific_version_id BINARY(16) NULL,
    priority INTEGER NOT NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_invoice_template_assignment PRIMARY KEY (id),
    CONSTRAINT fk_invoice_template_assignment_template_id FOREIGN KEY (template_id) REFERENCES invoice_template (id) ON DELETE CASCADE,
    CONSTRAINT fk_invoice_template_assignment_version_id FOREIGN KEY (specific_version_id) REFERENCES invoice_template_version (id) ON DELETE SET NULL,
    KEY ix_invoice_template_assignment_company (tenant_id, company_id),
    KEY ix_invoice_template_assignment_lookup (tenant_id, company_id, voucher_kind, is_active, priority),
    KEY ix_invoice_template_assignment_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_template_assignment")
