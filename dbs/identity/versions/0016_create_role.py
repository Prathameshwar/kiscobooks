"""create role

Revision ID: 0016
Revises: 0015

A named permission bundle (docs/identity-schema.md §5.1, docs/roles-permissions.md).
**Permissions are code, roles are data** (CLAUDE.md invariant 13): the key set is a
fixed catalogue in `billing_platform.permissions`, and this is the table a tenant
composes out of it.

`role` **and** `key` are MariaDB reserved words. Both are backticked here; the model's
generated SQL gets that from SQLAlchemy's dialect, and a test compiles `CreateTable`
under mysql to keep the two spellings in step.

Two departures from §5.1's field grid, both recorded in that doc's decision log:

* `tenant_id` is **NOT NULL**, and a system role carries `SCOPE_ALL`
  (`0x00…00`) rather than NULL (§2). The doc's `UNIQUE (tenant_id, key)` cannot work
  with NULLs — MariaDB treats them as distinct inside a unique index, so
  `billing_clerk` could be inserted as a system role any number of times. The session
  filter's exception is written for the sentinel: `tenant_id = :current OR tenant_id =
  SCOPE_ALL`, gated by `__tenant_shared__` rather than by table name.
* **No `is_system` column, and no `INDEX (is_system)`.** A stored flag can disagree
  with `tenant_id`, and the disagreement is an escalation: `is_system = 0` on a row
  with `tenant_id = SCOPE_ALL` is a platform-wide role a tenant may edit. Deriving it
  in the model makes that state unrepresentable rather than merely wrong, and
  `ix_role_tenant_id` already serves every query the dropped index would have.

`uq_role_id_tenant_id` exists only to be the parent of revision 0017's composite
foreign key. `id` is the primary key, so the pair is trivially unique — declared UNIQUE
to say so, rather than leaning on InnoDB's laxer requirement that a referenced index
merely lead with the referenced columns.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · `uq_role_tenant_id_key` is
16 + 60*4 + 1 = 257 bytes, well under 3072 (§1.6) · no NULL inside a unique key — that
is the point of the sentinel (§2) · no ENUM · no FLOAT · timestamps `DATETIME(6)`
suffixed `_at` · **no seed data**: the eleven system roles are `seeds/roles/`, never a
migration · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE `role` (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    `key` VARCHAR(60) NOT NULL,
    name VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,
    cloned_from_role_id BINARY(16) NULL,
    scope_hint VARCHAR(20) NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_role PRIMARY KEY (id),
    CONSTRAINT uq_role_tenant_id_key UNIQUE (tenant_id, `key`),
    CONSTRAINT uq_role_id_tenant_id UNIQUE (id, tenant_id),
    CONSTRAINT fk_role_cloned_from_role_id
        FOREIGN KEY (cloned_from_role_id) REFERENCES `role` (id),
    KEY ix_role_tenant_id (tenant_id),
    KEY ix_role_cloned_from_role_id (cloned_from_role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE `role`")
