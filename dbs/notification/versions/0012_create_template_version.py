"""Create template_version; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE template_version (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    template_variant_id BINARY(16) NOT NULL,
    version INT UNSIGNED NOT NULL,
    subject_text VARCHAR(998) NULL,
    body_text MEDIUMTEXT NOT NULL,
    body_html MEDIUMTEXT NULL,
    channel_payload JSON NULL,
    content_sha256 BINARY(32) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    CONSTRAINT pk_template_version PRIMARY KEY (id),
    CONSTRAINT uq_template_version_number UNIQUE (template_variant_id, version),
    CONSTRAINT uq_template_version_content UNIQUE (template_variant_id, content_sha256),
    CONSTRAINT fk_template_version_template_variant_id FOREIGN KEY (template_variant_id) REFERENCES template_variant (id),
    KEY ix_template_version_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE template_version")

