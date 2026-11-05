"""Create invoice_template_asset; brand graphics and fonts under a service-derived path."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE invoice_template_asset (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    asset_type VARCHAR(32) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(64) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    storage_backend VARCHAR(32) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    content_digest VARCHAR(64) NULL,
    image_width_px INTEGER NULL,
    image_height_px INTEGER NULL,
    is_active BOOL NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_invoice_template_asset PRIMARY KEY (id),
    KEY ix_invoice_template_asset_company (tenant_id, company_id),
    KEY ix_invoice_template_asset_lookup (tenant_id, company_id, is_active, asset_type),
    KEY ix_invoice_template_asset_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_template_asset")
