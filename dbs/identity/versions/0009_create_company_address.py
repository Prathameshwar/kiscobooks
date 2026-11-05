"""create company_address

Revision ID: 0009
Revises: 0008

Registered, billing, shipping and branch addresses for a company
(docs/identity-schema.md §3.5). Rows rather than columns because a company genuinely
has several, at different places.

Carries the same composite foreign key as `company`, and it matters at least as much
here: a shipping address's `state_code` is the place of supply for a goods invoice, so
an impossible `(country_code, state_code)` pair would tax the document wrongly. The
pair is refused by the database.

`ix_company_address_company_id_type` leads with `company_id` rather than `tenant_id`
(§1.7's foreign-key case). Two reasons that agree: `company_id` functionally
determines `tenant_id`, so a tenant-filtered query can still use the index; and an
index supporting `fk_company_address_company_id` must begin with that column, or
InnoDB creates a second, invisible one that then reads as autogenerate drift.

`is_primary` has **no unique constraint.** "At most one true per (company, type)"
needs a partial unique index, which MariaDB does not have (§2), so it is a `domain/`
rule. Note that `company.state_code` is deliberately *not* derived from the primary
registered address (docs/org-model.md §6.2): if it were, flipping `is_primary` here
would retroactively change the tax treatment of invoices already issued.

Lifecycle is `is_active` — rule 4.12's boolean form, never combined with a `status`.
An address does not affect a computed amount, so dates are not needed; deactivating
means "not selectable for new documents" and never hides an address a document was
already issued to.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no composite unique key at all, so
nothing to size against 3072 (§1.6) · no NULL inside a unique key (§2) · no ENUM ·
no FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_address (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    type VARCHAR(20) NOT NULL,
    label VARCHAR(100) NULL,
    line1 VARCHAR(255) NOT NULL,
    line2 VARCHAR(255) NULL,
    city VARCHAR(100) NOT NULL,
    state_code VARCHAR(6) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    country_code CHAR(2) NOT NULL,
    is_primary TINYINT(1) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    deactivated_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_address PRIMARY KEY (id),
    CONSTRAINT fk_company_address_company_id
        FOREIGN KEY (company_id) REFERENCES company (id),
    CONSTRAINT fk_company_address_country_code
        FOREIGN KEY (country_code) REFERENCES country (code),
    CONSTRAINT fk_company_address_country_code_state_code
        FOREIGN KEY (country_code, state_code) REFERENCES state (country_code, code),
    KEY ix_company_address_tenant_id (tenant_id),
    KEY ix_company_address_company_id_type (company_id, type),
    KEY ix_company_address_country_code_state_code (country_code, state_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_address")
