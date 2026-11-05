"""Create provider_template_binding; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE provider_template_binding (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    template_version_id BINARY(16) NOT NULL,
    provider_account_id BINARY(16) NOT NULL,
    external_template_id VARCHAR(255) NOT NULL,
    external_name VARCHAR(512) NOT NULL,
    external_language VARCHAR(35) NOT NULL,
    external_category VARCHAR(40) NULL,
    approval_status VARCHAR(20) NOT NULL,
    quality_status VARCHAR(20) NULL,
    rejection_code VARCHAR(120) NULL,
    rejection_detail VARCHAR(1000) NULL,
    submitted_at DATETIME(6) NULL,
    reviewed_at DATETIME(6) NULL,
    synced_at DATETIME(6) NOT NULL,
    CONSTRAINT pk_provider_template_binding PRIMARY KEY (id),
    CONSTRAINT uq_binding_provider_external UNIQUE (provider_account_id, external_template_id),
    CONSTRAINT uq_binding_version_provider UNIQUE (template_version_id, provider_account_id),
    CONSTRAINT fk_provider_template_binding_template_version_id FOREIGN KEY (template_version_id) REFERENCES template_version (id),
    CONSTRAINT fk_provider_template_binding_provider_account_id FOREIGN KEY (provider_account_id) REFERENCES provider_account (id),
    KEY ix_provider_template_binding_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE provider_template_binding")

