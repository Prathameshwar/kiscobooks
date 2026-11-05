"""Add encrypted bank details without destroying legacy values. One DDL."""
from alembic import op
from sqlalchemy import text
revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""ALTER TABLE company_bank_account
        ADD COLUMN details_ciphertext BLOB NULL,
        ADD COLUMN encryption_key_id VARCHAR(80) NULL,
        ADD COLUMN account_last4 VARCHAR(4) NULL,
        ADD COLUMN iban_last4 VARCHAR(4) NULL""")

def downgrade() -> None:
    # Removing encrypted data silently would make new accounts unrecoverable.
    if op.get_bind().execute(text("SELECT id FROM company_bank_account WHERE details_ciphertext IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("decrypt/backfill and archive bank details before a reviewed downgrade")
    op.execute("ALTER TABLE company_bank_account DROP COLUMN details_ciphertext, DROP COLUMN encryption_key_id, DROP COLUMN account_last4, DROP COLUMN iban_last4")
