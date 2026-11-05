"""Create invoice_render_snapshot; append-only print evidence whose parents never drop."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE invoice_render_snapshot (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    voucher_id BINARY(16) NOT NULL,
    voucher_revision_id BINARY(16) NULL,
    template_id BINARY(16) NOT NULL,
    template_version_id BINARY(16) NOT NULL,
    output_format VARCHAR(16) NOT NULL,
    render_channel VARCHAR(32) NOT NULL,
    storage_path VARCHAR(512) NULL,
    checksum_sha256 VARCHAR(64) NULL,
    file_size_bytes INTEGER NULL,
    render_duration_ms INTEGER NULL,
    rendered_by BINARY(16) NULL,
    rendered_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_invoice_render_snapshot PRIMARY KEY (id),
    CONSTRAINT fk_invoice_render_snapshot_template_id FOREIGN KEY (template_id) REFERENCES invoice_template (id) ON DELETE RESTRICT,
    CONSTRAINT fk_invoice_render_snapshot_version_id FOREIGN KEY (template_version_id) REFERENCES invoice_template_version (id) ON DELETE RESTRICT,
    KEY ix_invoice_render_snapshot_company (tenant_id, company_id),
    KEY ix_invoice_render_snapshot_voucher (tenant_id, voucher_id, rendered_at),
    KEY ix_invoice_render_snapshot_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_render_snapshot")
