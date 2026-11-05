"""Create bank_opening_item as one DDL statement."""

from alembic import op

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_opening_item (
	account_id BINARY(16) NOT NULL,
	instrument_id BINARY(16) NOT NULL,
	cutoff_date DATE NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_opening_item PRIMARY KEY (id),
	CONSTRAINT uq_bank_opening_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bank_opening_account FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT fk_bank_opening_instrument FOREIGN KEY(tenant_id, company_id, instrument_id) REFERENCES bank_instrument (tenant_id, company_id, id),
	CONSTRAINT uq_bank_opening_instrument UNIQUE (tenant_id, company_id, account_id, instrument_id),
	CONSTRAINT ck_bank_opening_item_bank_opening_amount CHECK (amount > 0)
,
	KEY ix_bank_opening_account (tenant_id, company_id, account_id, cutoff_date, id),
	KEY ix_bank_opening_item_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_opening_item")
