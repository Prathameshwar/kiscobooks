"""create company_licence

Revision ID: 0013
Revises: 0012

Trading licences that gate posting and print on documents — drug licences, FSSAI, LUT
(docs/identity-schema.md §3.8, docs/company.md §4.4). A licence is **behaviour, not a
text field**: a scheduled-drug line with no licence valid on the `posting_date` is
*rejected*, and the number printed on the invoice is the one that was in force then.

Date-effective for that reason (rule 4.12): a reprint of a two-year-old invoice must
show the licence valid then, not today's renewal. Never deleted.

`ix_company_licence_valid_to` is the one index in this phase that leads with neither
`tenant_id` nor `company_id`, and it is not a §1.7 exception so much as a different
query: the Beat expiry sweep asks "what expires soon" across every tenant, runs under
`unfiltered()` by construction, and is its only reader. A tenant-led index would be
useless to it.

The composite `(company_id, kind, valid_from, valid_to)` index leads with `company_id`
under §1.7's two exceptions, as elsewhere in this phase.

Several licences of one kind may be valid at once — licences are usually per premises —
so the unique key is `(company_id, kind, number, valid_from)`: a renewal reuses the
number with a new start date, which is what distinguishes the rows. `is_primary` has no
unique constraint; "at most one true per kind" needs a partial unique index, which
MariaDB does not have (§2).

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · composite unique is
16 + 40*4 + 60*4 + 3 = 419 bytes, well under 3072 (§1.6) · no NULL inside a unique key
(§2) · no ENUM · no FLOAT · `SMALLINT` not `TINYINT` for a day count · timestamps
`DATETIME(6)` suffixed `_at`, business dates `DATE` suffixed `_on`/`_from`/`_to` · no
seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE company_licence (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    company_id BINARY(16) NOT NULL,
    kind VARCHAR(40) NOT NULL,
    number VARCHAR(60) NOT NULL,
    issuing_authority VARCHAR(200) NULL,
    premises_address_id BINARY(16) NULL,
    issued_on DATE NULL,
    renewal_reminder_days SMALLINT NULL,
    document_url VARCHAR(500) NULL,
    is_primary TINYINT(1) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_licence PRIMARY KEY (id),
    CONSTRAINT uq_company_licence_company_id_kind_number_valid_from
        UNIQUE (company_id, kind, number, valid_from),
    CONSTRAINT fk_company_licence_company_id
        FOREIGN KEY (company_id) REFERENCES company (id),
    CONSTRAINT fk_company_licence_premises_address_id
        FOREIGN KEY (premises_address_id) REFERENCES company_address (id),
    KEY ix_company_licence_tenant_id (tenant_id),
    KEY ix_company_licence_company_id_kind_valid_from_valid_to
        (company_id, kind, valid_from, valid_to),
    KEY ix_company_licence_valid_to (valid_to),
    KEY ix_company_licence_premises_address_id (premises_address_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE company_licence")
