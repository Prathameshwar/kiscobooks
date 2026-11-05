"""create company_tax_registration

Revision ID: 0011
Revises: 0010

The registrations a company invoices under (docs/identity-schema.md §3.6,
docs/company.md §4.2). Date-effective rather than current-value, and rule 4.12 makes
that mandatory: `regime` decides whether tax may be charged at all, so a company that
moved from Composition to Regular on 1 October must still reprint an August invoice
showing Composition — the regime the filed return reported.

`valid_from`/`valid_to` therefore, never `is_active`, and no `DeactivableMixin`: an
invoice issued under an old GSTIN must resolve it years later, so rows are neither
deleted nor deactivated.

`uq_company_tax_registration_tax_system_jurisdiction_valid_from` is **named
explicitly**. The naming convention's generated name would be
`uq_company_tax_registration_company_id_tax_system_jurisdiction_code_valid_from` —
74 characters, past MariaDB's 64-character identifier limit (§1.3). `company_id` is
dropped from the name because the table prefix already says the row is company-owned,
and the `_code` suffix goes with it; the constraint itself still leads with
`company_id`. `ix_company_tax_registration_jurisdiction_validity` is shortened the
same way, collapsing `valid_from, valid_to` to `validity`.

Both composite keys lead with `company_id` rather than `tenant_id` — §1.7's two
exceptions, and they agree here as they did on `company_address`: an index supporting
`fk_company_tax_registration_company_id` must begin with that column or InnoDB
invents an invisible one, and `company_id` functionally determines `tenant_id`.

`jurisdiction_code` carries **no foreign key**, deliberately: it holds a state code
in India (one GSTIN per state) and a country code in the UK (one VAT number per
country), and no single target covers both. Which shape is required comes from the
jurisdiction profile and is checked in `domain/`.

Two rules the database cannot express, both in `domain/`: **overlapping validity for
one `(tax_system, jurisdiction_code)` pair is rejected at write time** — no DDL can
say "no two rows with intersecting date ranges", and the unique key here only stops
an exact duplicate — and **a gap resolves to `None`**, never to the nearest row.

`is_primary` has no unique constraint: "at most one true per jurisdiction" needs a
partial unique index, which MariaDB does not have (§2).

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · widest composite unique is
16 + 20*4 + 6*4 + 3 = 123 bytes, well under 3072 (§1.6) · no NULL inside a unique key
(§2) · no ENUM · no FLOAT · timestamps `DATETIME(6)` suffixed `_at`, business dates
`DATE` suffixed `_from`/`_to` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_tax_registration (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    tax_system VARCHAR(20) NOT NULL,
    regime VARCHAR(30) NOT NULL,
    number VARCHAR(40) NOT NULL,
    jurisdiction_code VARCHAR(6) NOT NULL,
    legal_name_on_registration VARCHAR(255) NULL,
    registered_address_id BINARY(16) NULL,
    is_primary TINYINT(1) NOT NULL,
    verified_at DATETIME(6) NULL,
    verified_by BINARY(16) NULL,
    verification_reference VARCHAR(120) NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_tax_registration PRIMARY KEY (id),
    CONSTRAINT uq_company_tax_registration_tax_system_jurisdiction_valid_from
        UNIQUE (company_id, tax_system, jurisdiction_code, valid_from),
    CONSTRAINT fk_company_tax_registration_company_id
        FOREIGN KEY (company_id) REFERENCES company (id),
    CONSTRAINT fk_company_tax_registration_registered_address_id
        FOREIGN KEY (registered_address_id) REFERENCES company_address (id),
    KEY ix_company_tax_registration_tenant_id (tenant_id),
    KEY ix_company_tax_registration_jurisdiction_validity
        (company_id, jurisdiction_code, valid_from, valid_to),
    KEY ix_company_tax_registration_registered_address_id (registered_address_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_tax_registration")
