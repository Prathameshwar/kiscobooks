"""Add company_tax_registration.registration_class. One DDL statement per direction.

docs/company.md §4.2. The class (``billing_platform.tax.REGISTRATION_CLASSES``) is a
property of the regime; it is stored so the unique key can group by it as the overlap
rule already does (revision 0063). Added ``NOT NULL DEFAULT 'supplier'`` so existing
rows get a value without a table rebuild — ``supplier`` is the catalogue's default
class. Revision 0061 backfills the other classes from the catalogue and 0062 drops
the default, so no insert can classify a row by omission.

Checklist: one DDL statement · VARCHAR, not ENUM · instant ADD COLUMN · no seed data ·
downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE company_tax_registration "
        "ADD COLUMN registration_class VARCHAR(20) NOT NULL DEFAULT 'supplier'"
    )


def downgrade() -> None:
    # Safe: the class is derived from `regime`, which stays, so nothing is lost.
    op.execute("ALTER TABLE company_tax_registration DROP COLUMN registration_class")
