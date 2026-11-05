"""Widen company_tax_registration's unique key to include registration_class.

docs/company.md §4.2. The old key ``(company_id, tax_system, jurisdiction_code,
valid_from)`` refused a regular GSTIN and a TDS-deductor (or ISD, or TCS) registration
in one state starting the same day, although the overlap rule allows them to coexist.
The new key groups exactly as ``assert_no_overlap`` does.

One ``ALTER TABLE`` with both clauses, so the swap is atomic: there is no moment with
no key. The new key still leads with ``company_id`` and so still supports
``fk_company_tax_registration_company_id`` (as does
``ix_company_tax_registration_jurisdiction_validity``). Widest key: 16 + 20*4 + 20*4 +
6*4 + 3 = 203 bytes, well under 3072. The name is shortened by hand (57 characters)
for MariaDB's 64-character limit.

Checklist: one DDL statement per direction · no NULL in the key · downgrade present,
refusing rather than failing half-way when rows the old key forbids exist.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063"
down_revision: str | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE company_tax_registration
    DROP INDEX uq_company_tax_registration_tax_system_jurisdiction_valid_from,
    ADD CONSTRAINT uq_company_tax_registration_class_jurisdiction_valid_from
        UNIQUE (company_id, tax_system, registration_class, jurisdiction_code, valid_from)
"""
    )


def downgrade() -> None:
    # Restoring the narrower key would fail on same-day registrations of different
    # classes; refuse explicitly instead of failing inside the ALTER.
    collision = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM company_tax_registration "
                "GROUP BY company_id, tax_system, jurisdiction_code, valid_from "
                "HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .scalar()
    )
    if collision is not None:
        raise RuntimeError(
            "same-day registrations of different classes exist; close or move one "
            "before downgrading below 0063"
        )
    op.execute(
        """
ALTER TABLE company_tax_registration
    DROP INDEX uq_company_tax_registration_class_jurisdiction_valid_from,
    ADD CONSTRAINT uq_company_tax_registration_tax_system_jurisdiction_valid_from
        UNIQUE (company_id, tax_system, jurisdiction_code, valid_from)
"""
    )
