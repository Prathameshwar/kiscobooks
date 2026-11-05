"""create country

Revision ID: 0005
Revises: 0004

ISO 3166-1 (docs/identity-schema.md §1.1). Selects the jurisdiction profile that
drives which statutory IDs and licences a company must supply.

`default_currency_code` carries a real foreign key to `currency.code`. Worth stating
why, since most references in this schema deliberately do not: both tables live in
this database, both are seeded together from the same source, and neither is written
by a request path — so the FK costs nothing and makes a currency code that does not
exist unrepresentable. The `tenant_id` and `*_by` columns elsewhere are unindexed by
comparison for reasons specific to them (§1.4, §1.5), not from a blanket
no-foreign-keys rule.

`ix_country_default_currency_code` is declared **explicitly**. InnoDB requires an
index on the referencing column and silently creates one named after the constraint
if none exists; that index would be absent from the models and would show up as
autogenerate drift on the next revision.

`subdivision_label` is `VARCHAR(60)`, widened from the 40 first written in
docs/identity-schema.md §1.1 — see that doc's decision log. ISO 3166-2 subdivision
type names run to 45 characters, and MariaDB truncates an over-long value rather
than raising it.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · PK 8 bytes and the FK index 12, well
under 3072 (§1.6) · no ENUM · no FLOAT · no NULL inside a key · no seed data —
content is `seeds/reference/` · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The FK has no ON DELETE clause, so it is RESTRICT: a currency row is never
# deleted, and an attempt to delete one still referenced must fail loudly rather
# than cascade into 239 country rows or null a NOT NULL column.
#
# `name` is the common name for UI ("India"); `official_name` is the legal name for
# printed documents ("Republic of India"). Both are needed — an invoice footer uses
# the second and a dropdown the first.
_CREATE = """
CREATE TABLE country (
    code CHAR(2) NOT NULL,
    iso3 CHAR(3) NOT NULL,
    numeric_code CHAR(3) NOT NULL,
    name VARCHAR(100) NOT NULL,
    official_name VARCHAR(200) NOT NULL,
    default_currency_code CHAR(3) NOT NULL,
    phone_prefix VARCHAR(8) NOT NULL,
    subdivision_label VARCHAR(60) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    CONSTRAINT pk_country PRIMARY KEY (code),
    CONSTRAINT fk_country_default_currency_code
        FOREIGN KEY (default_currency_code) REFERENCES currency (code),
    KEY ix_country_default_currency_code (default_currency_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE country")
