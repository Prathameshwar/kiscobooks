"""Index document references for duplicate detection; one DDL statement."""

from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_voucher_reference_lookup", "voucher_reference", ["tenant_id", "company_id", "purpose", "reference"])


def downgrade() -> None:
    # Lookup index only; the revision foreign key keeps its own supporting key.
    op.drop_index("ix_voucher_reference_lookup", table_name="voucher_reference")
