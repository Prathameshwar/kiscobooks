"""create role_permission

Revision ID: 0017
Revises: 0016

Which catalogue keys a role grants (docs/identity-schema.md §5.2).

`permission_key` is a plain `VARCHAR` with **no foreign key**, because there is no
`permission` table: permissions are a fixed catalogue in code (CLAUDE.md invariant 13).
The compensating control for the missing constraint is the **boot check** — a stored key
absent from `billing_platform.permissions.PERMISSIONS` fails startup, because a role
granting a key no code recognizes grants nothing, silently, forever.

**This table carries `tenant_id`, which §5.2's mixin list omits** — a documented
departure. A child with no `tenant_id` sits outside the session-level filter, so every
read would have to remember to join through `role` and constrain the parent: per-query
discipline, which CLAUDE.md §5.3 forbids precisely because one forgotten join is a
leak.

The column is not a duplicate to keep in step by hand. `fk_role_permission_role_id_tenant_id`
is composite — `(role_id, tenant_id)` → `role (id, tenant_id)` — so a row whose
`tenant_id` disagrees with its role's is unstorable. Without it a tenant could attach a
permission row to another tenant's role and the filter would show it to them as their
own. It also means the system roles' permission rows sit at `SCOPE_ALL` alongside their
roles, which is why the model sets `__tenant_shared__` here too: without that the
eleven shipped roles resolve to the empty set.

`ix_role_permission_role_id_tenant_id` leads with `role_id` rather than `tenant_id`,
under §1.7's first exception — an index supporting a foreign key must lead with the FK's
own columns in the FK's order, or InnoDB invents one named after the constraint and
autogenerate reports it as drift forever. It is also the shape of the resolution query:
this role's keys, then the injected tenant filter.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · `uq_role_permission_role_id_permission_key`
is 16 + 80*4 = 336 bytes, well under 3072 (§1.6) · no NULL inside a unique key (§2) ·
no ENUM · no FLOAT · timestamps `DATETIME(6)` suffixed `_at` · **no seed data**: the
shipped grants are `seeds/roles/` · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE role_permission (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    role_id BINARY(16) NOT NULL,
    permission_key VARCHAR(80) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_role_permission PRIMARY KEY (id),
    CONSTRAINT uq_role_permission_role_id_permission_key UNIQUE (role_id, permission_key),
    CONSTRAINT fk_role_permission_role_id_tenant_id
        FOREIGN KEY (role_id, tenant_id) REFERENCES `role` (id, tenant_id),
    KEY ix_role_permission_tenant_id (tenant_id),
    KEY ix_role_permission_role_id_tenant_id (role_id, tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE role_permission")
