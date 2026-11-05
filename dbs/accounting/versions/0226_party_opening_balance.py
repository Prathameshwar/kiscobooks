"""party_opening_balance: one atomic CREATE TABLE."""
from alembic import op
from sqlalchemy import text
revision = "0226"
down_revision = "0225"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE party_opening_balance (
    party_id BINARY(16) NOT NULL,
    role VARCHAR(20) NOT NULL,
    account_id BINARY(16) NOT NULL,
    source_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL,
    exchange_rate NUMERIC(19, 8) NOT NULL,
    base_amount NUMERIC(19, 4) NOT NULL,
    document_kind VARCHAR(20),
    document_reference VARCHAR(120) NOT NULL,
    document_date DATE,
    due_date DATE,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_party_opening_balance PRIMARY KEY (id),
    CONSTRAINT uq_party_opening_balance_source UNIQUE (tenant_id, company_id, source_key),
    CONSTRAINT uq_party_opening_balance_account UNIQUE (tenant_id, company_id, account_id),
    CONSTRAINT ck_party_opening_balance_party_opening_balance_status CHECK (status IN ('PENDING', 'WITHDRAWN')),
    CONSTRAINT ck_party_opening_balance_party_opening_balance_role CHECK (role IN ('CUSTOMER', 'SUPPLIER')),
    CONSTRAINT ck_party_opening_balance_party_opening_balance_side CHECK (side IN ('DEBIT', 'CREDIT')),
    CONSTRAINT ck_party_opening_balance_party_opening_balance_values CHECK (amount > 0 AND base_amount > 0 AND exchange_rate > 0),
    CONSTRAINT ck_party_opening_balance_party_opening_balance_kind CHECK (document_kind IS NULL OR document_kind IN ('ON_ACCOUNT', 'INVOICE', 'BILL', 'ADVANCE', 'CREDIT_NOTE')),
    CONSTRAINT uq_party_opening_balance_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_party_opening_balance_party_opening_balance_version CHECK (row_version > 0),
    CONSTRAINT fk_party_opening_balance_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
    CONSTRAINT fk_party_opening_balance_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id)
,
KEY ix_party_opening_balance_status (tenant_id, company_id, status, id),
KEY ix_party_opening_balance_party (tenant_id, company_id, party_id, id),
KEY ix_party_opening_balance_page (tenant_id, company_id, id),
KEY ix_party_opening_balance_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM party_opening_balance LIMIT 1")).first():
        raise RuntimeError("archive party opening balances before downgrade")
    op.execute("DROP TABLE party_opening_balance")
