"""create custom_field_definition

Revision ID: 0031
Revises: 0030

A runtime-configurable field (docs/identity-schema.md §6.1). ``key`` is immutable after
create and backticked (reserved word). ``company_id`` is NOT NULL and stores ``SCOPE_ALL``
for a tenant-wide definition (§2) — a NULL there would let two tenant-wide definitions with
the same key both insert. Unique-key name hand-shortened under 64 chars (§1.3).

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a
unique key · no ENUM · no FLOAT · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE custom_field_definition (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    `key` VARCHAR(60) NOT NULL,
    label VARCHAR(150) NOT NULL,
    help_text VARCHAR(500) NULL,
    placeholder VARCHAR(150) NULL,
    data_type VARCHAR(30) NOT NULL,
    display_order SMALLINT NOT NULL,
    display_group VARCHAR(100) NULL,
    is_searchable TINYINT(1) NOT NULL,
    is_immutable_after_create TINYINT(1) NOT NULL,
    requires_feature VARCHAR(60) NULL,
    validation JSON NULL,
    options JSON NULL,
    option_source_key VARCHAR(80) NULL,
    depends_on_key VARCHAR(60) NULL,
    visibility JSON NULL,
    sequence_config JSON NULL,
    default_value VARCHAR(500) NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_custom_field_definition PRIMARY KEY (id),
    CONSTRAINT uq_custom_field_def_scope_key UNIQUE (tenant_id, company_id, entity_type, `key`),
    KEY ix_custom_field_definition_tenant_id (tenant_id),
    KEY ix_custom_field_def_tenant_entity_active (tenant_id, entity_type, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_definition")
