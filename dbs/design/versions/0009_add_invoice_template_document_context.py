"""Add invoice_template.voucher_kind and line_profile: what a design is for (plan P1).

One ``ALTER TABLE`` is one DDL statement, so both columns land or neither does (rule 4.8).
Both are nullable: a template made before templates recorded their purpose stays routable
by any kind, exactly as it was.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE invoice_template "
        "ADD COLUMN voucher_kind VARCHAR(50) NULL AFTER is_system, "
        "ADD COLUMN line_profile VARCHAR(16) NULL AFTER voucher_kind"
    )


def downgrade() -> None:
    # Dropping loses only what a design says it is for; layouts, versions and rules stay.
    op.execute("ALTER TABLE invoice_template DROP COLUMN line_profile, DROP COLUMN voucher_kind")
