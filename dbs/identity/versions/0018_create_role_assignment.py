"""create role_assignment

Revision ID: 0018
Revises: 0017

The `(subject, role, scope)` triple that is the whole authorization model
(docs/identity-schema.md §5.3). Resolution is the union of every assignment whose scope
is an **ancestor-or-self** of the object being touched — `billing_platform.authz`, whose
only input is these rows.

`scope_id` is **NOT NULL and tenant scope stores `SCOPE_ALL`**, where §5.3 has NULL
(§2). The unique key contains `scope_id`, and MariaDB treats NULLs inside a unique index
as distinct, so one user could be granted `tenant_admin` tenant-wide any number of
times — each row a separate revocation somebody has to find. The API continues to accept
and return `null`; the sentinel never crosses the boundary.

`uq_role_assignment_subject_role_scope` is shortened. The name this convention would
produce — `uq_role_assignment_subject_type_subject_id_role_id_scope_type_scope_id` — is
70 characters, past the 64-character limit (§1.3), so a `<thing>_type, <thing>_id` pair
collapses to `<thing>`. The name therefore no longer lists its columns, and a test
asserts them instead.

`fk_role_assignment_role_id` is a **plain** foreign key, not the composite one revision
0017 uses. A tenant legitimately assigns a system role, so the two `tenant_id` values
differ by design and requiring them to agree would make the eleven shipped roles
unassignable.

`subject_id` and `scope_id` carry no foreign key: each points at one of two tables
depending on its `_type` column, and `scope_id` at neither when it holds the sentinel.
No single constraint expresses that. The compensating check is in `domain/` — both are
resolved before the row is written, never trusted from the request.

Both of rule 4.12's date-shaped mechanisms sit on this row and that is not the rule's
two competing lifecycles: `is_active = 0` is **revocation**, which must take effect the
moment it is written, and `valid_from`/`valid_to` is **scheduled elevation** — the
year-end auditor whose access lapses on a date rather than when someone remembers. Both
must pass, so neither can override the other in the permissive direction.

Every write here is a `security`-category audit event, and the three escalation guards
(docs/roles-permissions.md §1.5) are what stand between this table and self-promotion.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · the composite unique is
12*4 + 16 + 16 + 12*4 + 16 = 144 bytes, well under 3072 (§1.6) · no NULL inside a unique
key — that is the point of the sentinel (§2) · no ENUM · no FLOAT · timestamps
`DATETIME(6)` suffixed `_at`, business dates `DATE` suffixed `_from`/`_to` · no seed
data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE role_assignment (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    subject_type VARCHAR(12) NOT NULL,
    subject_id BINARY(16) NOT NULL,
    role_id BINARY(16) NOT NULL,
    scope_type VARCHAR(12) NOT NULL,
    scope_id BINARY(16) NOT NULL,
    granted_by BINARY(16) NULL,
    grant_reason VARCHAR(500) NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_role_assignment PRIMARY KEY (id),
    CONSTRAINT uq_role_assignment_subject_role_scope
        UNIQUE (subject_type, subject_id, role_id, scope_type, scope_id),
    CONSTRAINT fk_role_assignment_role_id FOREIGN KEY (role_id) REFERENCES `role` (id),
    KEY ix_role_assignment_tenant_id (tenant_id),
    KEY ix_role_assignment_tenant_id_subject (tenant_id, subject_type, subject_id),
    KEY ix_role_assignment_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE role_assignment")
