"""Create invoice_template_version; immutable layout snapshots."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE invoice_template_version (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    template_id BINARY(16) NOT NULL,
    version_number INTEGER NOT NULL,
    schema_version VARCHAR(16) NOT NULL,
    layout_definition JSON NOT NULL,
    layout_digest VARCHAR(64) NOT NULL,
    change_summary VARCHAR(255) NULL,
    published_at DATETIME(6) NULL,
    published_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    CONSTRAINT pk_invoice_template_version PRIMARY KEY (id),
    CONSTRAINT uq_invoice_template_version_number UNIQUE (template_id, version_number),
    CONSTRAINT fk_invoice_template_version_template_id FOREIGN KEY (template_id) REFERENCES invoice_template (id) ON DELETE CASCADE,
    KEY ix_invoice_template_version_template (tenant_id, template_id),
    KEY ix_invoice_template_version_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_template_version")
