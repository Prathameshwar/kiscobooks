"""create field_config

Revision ID: 0032
Revises: 0031

Per-tenant/company form layout for native and custom fields (docs/identity-schema.md
§6.2) — layout, not authorization. ``company_id`` is NOT NULL and stores ``SCOPE_ALL`` for
a tenant-wide config (§2). ``definition_id`` FKs the custom-field definition and gets its
own supporting index. Unique-key name hand-shortened under 64 chars (§1.3).

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a
unique key · no ENUM · no FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data ·
downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE field_config (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    field_source VARCHAR(10) NOT NULL,
    field_key VARCHAR(120) NOT NULL,
    definition_id BINARY(16) NULL,
    is_visible TINYINT(1) NULL,
    is_required TINYINT(1) NULL,
    display_order SMALLINT NULL,
    display_group VARCHAR(100) NULL,
    label_override VARCHAR(150) NULL,
    help_text_override VARCHAR(500) NULL,
    default_value VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_field_config PRIMARY KEY (id),
    CONSTRAINT uq_field_config_scope_entity_field
        UNIQUE (tenant_id, company_id, entity_type, field_key),
    CONSTRAINT fk_field_config_definition_id
        FOREIGN KEY (definition_id) REFERENCES custom_field_definition (id),
    KEY ix_field_config_tenant_id (tenant_id),
    KEY ix_field_config_tenant_id_entity_type (tenant_id, entity_type),
    KEY ix_field_config_definition_id (definition_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE field_config")
