"""create field_policy

Revision ID: 0030
Revises: 0029

Field-level allow/deny layered on role permissions (docs/identity-schema.md §5.4,
docs/field-permissions.md). It narrows, never widens. ``scope_id`` is NOT NULL and stores
``SCOPE_ALL`` at tenant scope (§2) — a NULL there would let two contradictory tenant-wide
policies for one field both insert, and the resolver would pick arbitrarily.
``subject_id``/``scope_id`` carry no FK (polymorphic). The unique-key name is hand-shortened
under the 64-char limit (§1.3); a test asserts its columns.

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a
unique key (that is the SCOPE_ALL point) · no ENUM · no FLOAT · no seed data · downgrade
present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE field_policy (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    subject_type VARCHAR(12) NOT NULL,
    subject_id BINARY(16) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    field_key VARCHAR(120) NOT NULL,
    access VARCHAR(10) NOT NULL,
    effect VARCHAR(10) NOT NULL,
    scope_type VARCHAR(12) NOT NULL,
    scope_id BINARY(16) NOT NULL,
    `condition` JSON NULL,
    reason VARCHAR(500) NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_field_policy PRIMARY KEY (id),
    CONSTRAINT uq_field_policy_subject_entity_field_access_scope
        UNIQUE (subject_type, subject_id, entity_type, field_key, access, scope_type, scope_id),
    KEY ix_field_policy_tenant_id (tenant_id),
    KEY ix_field_policy_tenant_id_subject (tenant_id, subject_type, subject_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE field_policy")
