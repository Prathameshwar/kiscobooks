"""Drop the ``'supplier'`` default from company_tax_registration.registration_class.

The default only existed to fill rows during revisions 0060 and 0061. Left in place, an
insert that forgot the column would silently classify a TDS-deductor or TCS row as a
supplier and let it collide with the regular GSTIN; without it, the insert fails.
``domain/`` sets the class on create (``registration_class_of``).

Checklist: one DDL statement per direction · metadata-only change · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE company_tax_registration ALTER COLUMN registration_class DROP DEFAULT")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE company_tax_registration "
        "ALTER COLUMN registration_class SET DEFAULT 'supplier'"
    )
