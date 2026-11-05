"""Extend the shared issue series; one DDL statement per direction."""

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_number_series "
        "ADD COLUMN suffix VARCHAR(20) NOT NULL DEFAULT '', "
        "ADD COLUMN start_value BIGINT NOT NULL DEFAULT 1, "
        "ADD COLUMN numbering_mode VARCHAR(30) NOT NULL DEFAULT 'AUTOMATIC', "
        "ADD COLUMN reset_policy VARCHAR(20) NOT NULL DEFAULT 'FINANCIAL_YEAR', "
        "ADD COLUMN include_year TINYINT(1) NOT NULL DEFAULT 1, "
        "ADD CONSTRAINT ck_voucher_number_series_start_value "
        "CHECK (start_value >= 1 AND start_value < 9223372036854775807), "
        "ADD CONSTRAINT ck_voucher_number_series_mode "
        "CHECK (numbering_mode IN ('AUTOMATIC','AUTOMATIC_WITH_OVERRIDE','MANUAL')), "
        "ADD CONSTRAINT ck_voucher_number_series_reset "
        "CHECK (reset_policy IN ('FINANCIAL_YEAR','NEVER'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE voucher_number_series "
        "DROP CHECK ck_voucher_number_series_reset, "
        "DROP CHECK ck_voucher_number_series_mode, "
        "DROP CHECK ck_voucher_number_series_start_value, "
        "DROP COLUMN include_year, "
        "DROP COLUMN reset_policy, "
        "DROP COLUMN numbering_mode, "
        "DROP COLUMN start_value, "
        "DROP COLUMN suffix"
    )
