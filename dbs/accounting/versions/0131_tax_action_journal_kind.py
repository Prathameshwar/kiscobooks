"""Native tax actions use the existing journal posting boundary; one atomic ALTER."""

from alembic import op

revision = "0131"
down_revision = "0130"
branch_labels = None
depends_on = None

OLD = "'MANUAL', 'OPENING', 'INVOICE', 'BILL', 'RECEIPT', 'PAYMENT', 'CREDIT_NOTE', 'CHARGE', 'REVERSAL', 'REALIZED_FX', 'VOUCHER'"
NAME = "ck_journal_journal_kind"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE journal DROP CHECK {NAME}, ADD CONSTRAINT {NAME} CHECK (kind IN ({OLD}, 'TAX_ACTION'))"
    )


def downgrade() -> None:
    # Refuse when tax-action journals exist; never relabel their financial provenance.
    op.execute(
        f"ALTER TABLE journal DROP CHECK {NAME}, ADD CONSTRAINT {NAME} CHECK (kind IN ({OLD}))"
    )
