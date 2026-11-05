"""Backfill company_tax_registration.registration_class from the Regime catalogue.

Data only, no DDL: every row was given ``supplier`` by revision 0060; this sets the
regimes the catalogue (``billing_platform.tax.REGIMES``) puts in another class —
``isd``, ``tds_deductor``, ``ecommerce_operator`` (``tcs_collector``). One
parameterized ``UPDATE`` per such regime. A regime the catalogue does not know keeps
``supplier``, matching ``billing_platform.tax.registration_class``'s fallback.

Rows are backfilled, never inserted: this is not seed data (seeds live in ``seeds/``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from billing_platform.tax import DEFAULT_REGISTRATION_CLASS, REGIMES

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SET_CLASS = sa.text(
    "UPDATE company_tax_registration SET registration_class = :registration_class "
    "WHERE tax_system = :tax_system AND regime = :regime"
)


def upgrade() -> None:
    # Bound parameters, never interpolation; `op.execute` also renders them for
    # offline (`--sql`) output.
    for tax_system, regimes in sorted(REGIMES.items()):
        for name, regime in sorted(regimes.items()):
            if regime.registration_class != DEFAULT_REGISTRATION_CLASS:
                op.execute(
                    _SET_CLASS.bindparams(
                        registration_class=regime.registration_class,
                        tax_system=tax_system,
                        regime=name,
                    )
                )


def downgrade() -> None:
    # No downgrade needed: the values are derived from `regime`, revision 0060's
    # downgrade drops the column, and re-running this upgrade is idempotent.
    pass
