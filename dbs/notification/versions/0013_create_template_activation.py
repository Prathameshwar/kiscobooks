"""Create template_activation; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE template_activation (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    template_variant_id BINARY(16) NOT NULL,
    template_version_id BINARY(16) NOT NULL,
    valid_from DATETIME(6) NOT NULL,
    valid_to DATETIME(6) NULL,
    activated_by BINARY(16) NULL,
    activation_reason VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_template_activation PRIMARY KEY (id),
    CONSTRAINT fk_template_activation_template_variant_id FOREIGN KEY (template_variant_id) REFERENCES template_variant (id),
    CONSTRAINT fk_template_activation_template_version_id FOREIGN KEY (template_version_id) REFERENCES template_version (id),
    KEY ix_template_activation_tenant_id (tenant_id),
    KEY ix_template_activation_variant_window (template_variant_id, valid_from, valid_to),
    KEY ix_template_activation_tenant_window (tenant_id, valid_from, valid_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE template_activation")

