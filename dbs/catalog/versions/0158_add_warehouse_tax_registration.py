"""Add nullable ``tax_registration_id`` to warehouse; one DDL.

Nullable because locations without GST/tax registration scoping (or outside India)
keep existing rows untouched. Scoped index ``ix_warehouse_tax_registration`` carries
``(tenant_id, company_id, tax_registration_id)`` to optimize ship-from Place of Supply
and registration resolution.
"""

from alembic import op

revision = "0158"
down_revision = "0157"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE warehouse "
    "ADD COLUMN tax_registration_id BINARY(16) NULL, "
    "ADD INDEX ix_warehouse_tax_registration (tenant_id, company_id, tax_registration_id)"
)


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE warehouse "
        "DROP INDEX ix_warehouse_tax_registration, "
        "DROP COLUMN tax_registration_id"
    )
