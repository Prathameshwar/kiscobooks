"""Create platform_price; commercial defaults are deployment seeds."""

from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE platform_price (
	code VARCHAR(40) NOT NULL,
	name VARCHAR(100) NOT NULL,
	category VARCHAR(20) NOT NULL,
	description VARCHAR(1000) NOT NULL,
	term_months INTEGER NOT NULL,
	unit VARCHAR(20) NOT NULL,
	currency_code VARCHAR(3) NOT NULL DEFAULT 'INR',
	monthly_fee DECIMAL(19,4) NOT NULL,
	unit_price DECIMAL(19,4) NOT NULL,
	output_unit_price DECIMAL(19,4) NOT NULL,
	tax_percent DECIMAL(19,4) NOT NULL,
	fx_inr_per_usd DECIMAL(19,4) NOT NULL,
	provider VARCHAR(60) NOT NULL,
	model VARCHAR(100) NOT NULL,
	version INTEGER NOT NULL,
	deleted_at DATETIME(6),
	id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	is_active BOOL NOT NULL,
	deactivated_at DATETIME(6),
	deactivated_by BINARY(16),
	CONSTRAINT pk_platform_price PRIMARY KEY (id),
	CONSTRAINT uq_platform_price_code UNIQUE (code),
	CONSTRAINT ck_platform_price_nonnegative_prices CHECK (monthly_fee >= 0 AND unit_price >= 0 AND output_unit_price >= 0),
	CONSTRAINT ck_platform_price_valid_conversion CHECK (fx_inr_per_usd > 0 AND tax_percent >= 0 AND tax_percent <= 100),
	CONSTRAINT ck_platform_price_valid_term_version CHECK (term_months IN (1, 12, 36) AND version > 0),
KEY ix_platform_price_deleted_code (deleted_at, code, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC""")


def downgrade() -> None:
    op.execute("DROP TABLE platform_price")
