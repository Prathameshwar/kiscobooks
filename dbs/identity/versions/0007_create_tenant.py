"""create tenant

Revision ID: 0007
Revises: 0006

The root isolation and subscription boundary (docs/identity-schema.md §3.1). First
table in the chain that is *domain* rather than mechanism or reference, and the first
one whose rows a user can see.

**No `tenant_id` column — `id` is the tenant id.** The session-level filter matches
this table on `id` via `SelfTenantMixin`, so it is inside the isolation boundary
rather than on the exemption whitelist. Getting that wrong here would expose a
tenant's name, slug, contact email and suspension reason to every other tenant.

`UNIQUE (slug)` is the only uniqueness constraint. `slug` is a DNS label, so
`VARCHAR(63)`, and it is immutable after creation — it appears in URLs, webhook
targets and bookmarks, and a rename silently breaks integrations. Immutability is
enforced in `domain/`, not by the schema: a NOT NULL unique column cannot express
"write once".

`status` rather than `is_active` (rule 4.12, one mechanism per entity). Suspension is
not deactivation — a suspended tenant still signs in to read `suspended_reason`.

`plan_id` carries **no foreign key**: `plan` is deferred pending the open question of
whether we bill our own tenants in this system (§3.2). Nullable until it exists; the
FK arrives with that table, in its own revision. An FK to a table that does not exist
yet is the one thing this chain cannot express.

Two foreign keys, to `country` and `currency`, with their supporting indexes declared
explicitly. InnoDB would create them itself and name them after the constraints, and
that invisible index then shows as autogenerate drift on every later revision.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · `uq_tenant_slug` is 252 bytes, well
under 3072 (§1.6) · no NULL inside a unique key (§2) · no ENUM · no FLOAT · no seed
data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE tenant (
    id BINARY(16) NOT NULL,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(63) NOT NULL,
    status VARCHAR(20) NOT NULL,
    plan_id BINARY(16) NULL,
    primary_contact_email VARCHAR(320) NOT NULL,
    default_country_code CHAR(2) NOT NULL,
    default_currency_code CHAR(3) NOT NULL,
    default_locale VARCHAR(8) NOT NULL,
    default_timezone VARCHAR(64) NOT NULL,
    trial_ends_on DATE NULL,
    suspended_at DATETIME(6) NULL,
    suspended_reason VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_tenant PRIMARY KEY (id),
    CONSTRAINT uq_tenant_slug UNIQUE (slug),
    CONSTRAINT fk_tenant_default_country_code
        FOREIGN KEY (default_country_code) REFERENCES country (code),
    CONSTRAINT fk_tenant_default_currency_code
        FOREIGN KEY (default_currency_code) REFERENCES currency (code),
    KEY ix_tenant_default_country_code (default_country_code),
    KEY ix_tenant_default_currency_code (default_currency_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE tenant")
