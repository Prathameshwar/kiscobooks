"""create state

Revision ID: 0006
Revises: 0005

ISO 3166-2 subdivisions (docs/identity-schema.md §1.2). Required for tax
place-of-supply, and carries the GST state code that prefixes every GSTIN issued in
that state.

**`uq_state_country_code_code` is load-bearing and looks redundant.** `code` is
already the primary key, so a unique key on `(country_code, code)` adds no
uniqueness. It exists to be the *target* of the composite foreign key that `company`
and `company_address` will declare on `(country_code, state_code)` in phase 3 — a
foreign key needs a unique index over exactly its referenced columns. That composite
FK is what makes `country_code='IN'` with `state_code='US-CA'` unrepresentable
rather than merely unlikely, which is a class of tax-jurisdiction bug that no
validation layer catches reliably. Do not remove this key for looking duplicated.

It also serves the `country_code` foreign key: InnoDB accepts a leftmost prefix of
an existing index, so no separate `KEY (country_code)` is needed and none is
declared — one would be a second index on the same prefix, and autogenerate would
propose dropping it forever.

`subdivision_type` is `VARCHAR(60)`, widened from the 40 first written in
docs/identity-schema.md §1.2 — see that doc's decision log. "Metropolitan
collectivity with special status" is 45 characters, and MariaDB truncates an
over-long value on insert rather than raising, so the narrower column would have
seeded silently wrong data.

`tax_jurisdiction_code` is nullable: only India assigns one. Nullable here is safe
because the column is in no key — the "no NULL inside a UNIQUE key" rule (§2) is
about MariaDB treating NULLs as distinct, which does not apply.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · unique key 32 bytes, well under 3072
(§1.6) · no ENUM · no FLOAT · no seed data — content is `seeds/reference/` ·
downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Dropped in the reverse order of creation across 0004-0006, which the linear chain
# gives for free: `state` before `country` before `currency`, so no downgrade ever
# tries to drop a table another still references.
_CREATE = """
CREATE TABLE state (
    code VARCHAR(6) NOT NULL,
    country_code CHAR(2) NOT NULL,
    name VARCHAR(100) NOT NULL,
    subdivision_type VARCHAR(60) NOT NULL,
    tax_jurisdiction_code VARCHAR(8) NULL,
    is_active TINYINT(1) NOT NULL,
    CONSTRAINT pk_state PRIMARY KEY (code),
    CONSTRAINT uq_state_country_code_code UNIQUE (country_code, code),
    CONSTRAINT fk_state_country_code FOREIGN KEY (country_code) REFERENCES country (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE state")
