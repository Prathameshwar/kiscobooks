"""create currency

Revision ID: 0004
Revises: 0003

ISO 4217 plus the presentation metadata needed to print an amount
(docs/identity-schema.md §1.3).

First of the three reference tables because `country` points at it. The chain is
ordered by dependency, not by importance: a foreign key cannot be declared before
its target table exists, and there is no transactional DDL to unwind a half-applied
pair.

**Natural-code primary key**, `CHAR(3)`, not UUIDv7 — the one documented exception
(CLAUDE.md §4). `INR` is `INR` in every service database, every export and every log
line, and codes are never renamed.

**No `tenant_id`**: reference data is shared across tenants, so the table is on the
`TENANT_FILTER_EXEMPT` whitelist in `libs/platform` with its reason stated (§0.3).
**No `Audit` mixin**: content arrives by seed, so there is no actor to record.

`minor_unit` is display and rounding scale only. Storage stays `DECIMAL(19,4)`
everywhere — a JPY amount is `1234.0000` and renders with no decimals (§0.4).
Reading this column as a storage scale is how a subledger stops tying.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · PK 12 bytes, well under 3072 (§1.6) ·
no ENUM · no FLOAT · no NULL inside a key · no seed data — content is
`seeds/reference/` · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `symbol` is VARCHAR(8) rather than (1): a symbol is multi-byte in utf8mb4, and
# several currencies have no symbol at all and fall back to their code.
#
# `minor_unit_name` and its plural are nullable because CLDR has no systematic
# source for them; they are curated only where amount-in-words needs them.
#
# `is_active` is TINYINT(1) — MariaDB has no native boolean (§0.1). It means "not
# selectable for new records" and never hides an existing reference: a withdrawn
# code is deactivated by the seed, never deleted, because posted documents point at
# it (CLAUDE.md invariant 12).
_CREATE = """
CREATE TABLE currency (
    code CHAR(3) NOT NULL,
    numeric_code CHAR(3) NOT NULL,
    name VARCHAR(100) NOT NULL,
    symbol VARCHAR(8) NOT NULL,
    minor_unit TINYINT NOT NULL,
    major_unit_name VARCHAR(40) NOT NULL,
    minor_unit_name VARCHAR(40) NULL,
    minor_unit_name_plural VARCHAR(40) NULL,
    is_active TINYINT(1) NOT NULL,
    CONSTRAINT pk_currency PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE currency")
