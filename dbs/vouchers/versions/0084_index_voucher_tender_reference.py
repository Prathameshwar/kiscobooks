"""Index tender references (cheque numbers, UTRs) for duplicate detection; one DDL statement."""

from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_voucher_tender_reference", "voucher_tender", ["tenant_id", "company_id", "reference"])


def downgrade() -> None:
    # Lookup index only; the revision foreign key keeps its own supporting key.
    op.drop_index("ix_voucher_tender_reference", table_name="voucher_tender")
