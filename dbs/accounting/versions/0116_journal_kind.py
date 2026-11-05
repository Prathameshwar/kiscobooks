"""Journal kind constraint; one atomic ALTER. Downgrade requires no VOUCHER rows."""
from alembic import op
revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE journal ADD CONSTRAINT ck_journal_journal_kind CHECK (kind IN ('MANUAL', 'OPENING', 'INVOICE', 'BILL', 'RECEIPT', 'PAYMENT', 'CREDIT_NOTE', 'CHARGE', 'REVERSAL', 'REALIZED_FX', 'VOUCHER'))")

def downgrade() -> None:
    op.execute('ALTER TABLE journal DROP CHECK ck_journal_journal_kind')
