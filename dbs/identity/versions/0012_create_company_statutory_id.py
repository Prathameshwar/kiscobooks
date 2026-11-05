"""create company_statutory_id

Revision ID: 0012
Revises: 0011

PAN, TAN, CIN, EIN, Udyam and their equivalents (docs/identity-schema.md §3.7,
docs/company.md §4.3). Rows rather than columns because the set is
jurisdiction-specific: a `pan` column is NULL for every company outside India, and a
new country would then be a migration instead of a profile entry.

**`value` is NULL for a restricted kind, and that is the design, not a gap.** AADHAAR
and SSN-class personal identity numbers are never stored (CLAUDE.md §5.10): the API
accepts a full number, `prepare_statutory_value` derives `value_last4` and the row
records a `verification_reference`, and the rest is discarded before it reaches a
model. PAN, TAN, CIN and EIN are *business* identifiers, print on invoices, and are
stored in full.

**`value_last4` is NOT NULL — for every kind, not only restricted ones**, and this
deviates from [identity-schema.md](../../../docs/identity-schema.md) §3.7's original
"Null: yes". It is the last column of `uq_company_statutory_id_company_id_kind_value_last4`,
and MariaDB treats NULLs inside a unique key as distinct (§2): left nullable and
unpopulated for unrestricted kinds, that constraint would let a company store the same
PAN twice while enforcing nothing at all. Keying on `value` instead is not an option —
it is NULL for exactly the kinds that matter most. Two different values of one kind
sharing their last four characters are falsely rejected; that is inherent in the
documented key and is the lesser failure.

Two lifecycle-shaped columns, one lifecycle. `is_active` is rule 4.12's mechanism
here, because an identifier prints and does not affect a computed amount. `valid_to`
is *data* — the expiry on the certificate — and carries no `valid_from`, so it cannot
be mistaken for the date-validity form.

`kind` carries no foreign key: kinds come from the code-defined jurisdiction profile,
and a `kind` table would let a tenant invent one no service can validate or print —
the same argument as `company_feature.feature_key`.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · composite unique is 16 + 40*4 + 4*4 = 192
bytes, well under 3072 (§1.6) · **no NULL inside a unique key** (§2) · no ENUM · no
FLOAT · timestamps `DATETIME(6)` suffixed `_at`, business dates `DATE` suffixed
`_on`/`_to` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_statutory_id (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    kind VARCHAR(40) NOT NULL,
    value VARCHAR(60) NULL,
    value_last4 VARCHAR(4) NOT NULL,
    holder_name VARCHAR(150) NULL,
    issued_on DATE NULL,
    valid_to DATE NULL,
    verified_at DATETIME(6) NULL,
    verified_by BINARY(16) NULL,
    verification_reference VARCHAR(120) NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_statutory_id PRIMARY KEY (id),
    CONSTRAINT uq_company_statutory_id_company_id_kind_value_last4
        UNIQUE (company_id, kind, value_last4),
    CONSTRAINT fk_company_statutory_id_company_id
        FOREIGN KEY (company_id) REFERENCES company (id),
    KEY ix_company_statutory_id_tenant_id (tenant_id),
    KEY ix_company_statutory_id_company_id_kind (company_id, kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_statutory_id")
