"""Import Sales, notes and money vouchers too: widen the job kind check; one DDL statement."""

from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

KINDS = (
    "'PURCHASE', 'SALES', 'CREDIT_NOTE', 'DEBIT_NOTE', 'PAYMENT', 'RECEIPT', 'CONTRA', 'JOURNAL'"
)


def upgrade() -> None:
    op.execute(f"""
ALTER TABLE voucher_import_job
    DROP CHECK ck_voucher_import_job_kind,
    ADD CONSTRAINT ck_voucher_import_job_kind CHECK (kind IN ({KINDS}))
""")


def downgrade() -> None:
    # Fails while other-kind jobs exist; purge or keep them before narrowing again.
    op.execute("""
ALTER TABLE voucher_import_job
    DROP CHECK ck_voucher_import_job_kind,
    ADD CONSTRAINT ck_voucher_import_job_kind CHECK (kind IN ('PURCHASE'))
""")
