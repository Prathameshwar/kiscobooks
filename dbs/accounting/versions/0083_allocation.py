"""allocation; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE allocation (
	debt_item_id BINARY(16) NOT NULL,
	credit_item_id BINARY(16) NOT NULL,
	posting_date DATE NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	base_currency VARCHAR(3) NOT NULL,
	debt_base_amount NUMERIC(19, 4) NOT NULL,
	credit_base_amount NUMERIC(19, 4) NOT NULL,
	fx_journal_id BINARY(16),
	reversal_date DATE,
	reversal_reason VARCHAR(500),
	fx_reversal_id BINARY(16),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_allocation PRIMARY KEY (id),
	CONSTRAINT ck_allocation_allocation_amount CHECK (amount > 0 AND debt_base_amount >= 0 AND credit_base_amount >= 0),
	CONSTRAINT ck_allocation_allocation_distinct CHECK (debt_item_id <> credit_item_id),
	CONSTRAINT ck_allocation_allocation_dates CHECK (reversal_date IS NULL OR reversal_date >= posting_date),
	CONSTRAINT uq_allocation_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_allocation_allocation_version CHECK (row_version > 0),
	CONSTRAINT fk_allocation_debt_item_id FOREIGN KEY(tenant_id, company_id, debt_item_id) REFERENCES open_item (tenant_id, company_id, id),
	CONSTRAINT fk_allocation_credit_item_id FOREIGN KEY(tenant_id, company_id, credit_item_id) REFERENCES open_item (tenant_id, company_id, id),
	CONSTRAINT fk_allocation_fx_journal_id FOREIGN KEY(tenant_id, company_id, fx_journal_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT fk_allocation_fx_reversal_id FOREIGN KEY(tenant_id, company_id, fx_reversal_id) REFERENCES journal (tenant_id, company_id, id),
	INDEX ix_allocation_credit (tenant_id, company_id, credit_item_id, posting_date, id),
	INDEX ix_allocation_debt (tenant_id, company_id, debt_item_id, posting_date, id),
	INDEX ix_allocation_page (tenant_id, company_id, id),
	INDEX ix_allocation_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE allocation"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
