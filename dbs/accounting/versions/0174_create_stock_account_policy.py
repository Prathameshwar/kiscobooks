"""Native stock authority: stock_account_policy; one reviewed reversible CREATE."""
from alembic import op

revision = "0174"
down_revision = "0173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_account_policy (
	valid_from DATE NOT NULL, 
	valid_to DATE, 
	inventory_account_id BINARY(16) NOT NULL, 
	receipt_clearing_account_id BINARY(16) NOT NULL, 
	dispatch_clearing_account_id BINARY(16) NOT NULL, 
	opening_offset_account_id BINARY(16) NOT NULL, 
	variance_account_id BINARY(16) NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_account_policy PRIMARY KEY (id), 
	CONSTRAINT uq_stock_account_policy_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_account_policy_stock_account_policy_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_account_policy_start UNIQUE (tenant_id, company_id, valid_from), 
	CONSTRAINT fk_stock_policy_inventory FOREIGN KEY(tenant_id, company_id, inventory_account_id) REFERENCES account (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_policy_receipt FOREIGN KEY(tenant_id, company_id, receipt_clearing_account_id) REFERENCES account (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_policy_dispatch FOREIGN KEY(tenant_id, company_id, dispatch_clearing_account_id) REFERENCES account (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_policy_opening FOREIGN KEY(tenant_id, company_id, opening_offset_account_id) REFERENCES account (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_policy_variance FOREIGN KEY(tenant_id, company_id, variance_account_id) REFERENCES account (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_account_policy_stock_account_policy_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	KEY ix_stock_account_policy_date (tenant_id, company_id, valid_from, id),
	KEY ix_stock_account_policy_dispatch_clearing_account_id (tenant_id, company_id, dispatch_clearing_account_id),
	KEY ix_stock_account_policy_inventory_account_id (tenant_id, company_id, inventory_account_id),
	KEY ix_stock_account_policy_opening_offset_account_id (tenant_id, company_id, opening_offset_account_id),
	KEY ix_stock_account_policy_page (tenant_id, company_id, id),
	KEY ix_stock_account_policy_receipt_clearing_account_id (tenant_id, company_id, receipt_clearing_account_id),
	KEY ix_stock_account_policy_tenant_id (tenant_id),
	KEY ix_stock_account_policy_variance_account_id (tenant_id, company_id, variance_account_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_account_policy")
