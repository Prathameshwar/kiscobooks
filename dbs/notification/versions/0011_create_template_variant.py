"""Create template_variant; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE template_variant (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    template_id BINARY(16) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    locale VARCHAR(35) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT pk_template_variant PRIMARY KEY (id),
    CONSTRAINT uq_template_variant_channel_locale UNIQUE (template_id, channel, locale),
    CONSTRAINT fk_template_variant_template_id FOREIGN KEY (template_id) REFERENCES notification_template (id),
    KEY ix_template_variant_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE template_variant")

