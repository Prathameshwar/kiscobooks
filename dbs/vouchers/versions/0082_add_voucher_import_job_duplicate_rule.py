"""Per-job duplicate bill rule (bill number and date, optionally supplier); one DDL statement.

A single ALTER TABLE adds the column and its check together; existing jobs keep the
supplier-inclusive default.
"""

from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE voucher_import_job
    ADD COLUMN duplicate_rule VARCHAR(30) NOT NULL DEFAULT 'DATE_NUMBER_PARTY',
    ADD CONSTRAINT ck_voucher_import_job_duplicate_rule
        CHECK (duplicate_rule IN ('DATE_NUMBER_PARTY', 'DATE_NUMBER', 'DATE_NUMBER_ACCOUNT'))
""")


def downgrade() -> None:
    # MySQL drops a column's CHECK constraint with the column in the same statement.
    op.execute("""
ALTER TABLE voucher_import_job
    DROP CHECK ck_voucher_import_job_duplicate_rule,
    DROP COLUMN duplicate_rule
""")
