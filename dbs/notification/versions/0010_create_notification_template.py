"""Create notification_template; one literal MySQL DDL statement per direction."""

from __future__ import annotations

from collections.abc import Sequence
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE notification_template (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    `key` VARCHAR(80) NOT NULL,
    event_key VARCHAR(120) NOT NULL,
    category VARCHAR(30) NOT NULL,
    description VARCHAR(500) NULL,
    default_locale VARCHAR(35) NOT NULL,
    variable_schema JSON NOT NULL,
    is_active TINYINT(1) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    CONSTRAINT pk_notification_template PRIMARY KEY (id),
    CONSTRAINT uq_notification_template_company_key UNIQUE (tenant_id, company_id, `key`),
    KEY ix_notification_template_tenant_id (tenant_id),
    KEY ix_notification_template_event (tenant_id, company_id, event_key, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE notification_template")

