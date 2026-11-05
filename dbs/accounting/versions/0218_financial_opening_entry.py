"""financial_opening_entry: one atomic CREATE TABLE."""
from alembic import op
from sqlalchemy import text
revision = "0218"
down_revision = "0217"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE financial_opening_entry (
    revision_id BINARY(16) NOT NULL,
    ordinal INTEGER NOT NULL,
    source_key VARCHAR(100) NOT NULL,
    account_id BINARY(16) NOT NULL,
    party_id BINARY(16),
    `role` VARCHAR(20),
    side VARCHAR(10) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL,
    base_amount NUMERIC(19, 4) NOT NULL,
    document_count INTEGER NOT NULL,
    payload JSON NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_financial_opening_entry PRIMARY KEY (id),
    CONSTRAINT uq_fin_open_entry_order UNIQUE (tenant_id, company_id, revision_id, ordinal),
    CONSTRAINT uq_fin_open_entry_source UNIQUE (tenant_id, company_id, revision_id, source_key),
    CONSTRAINT ck_financial_opening_entry_fin_open_entry_values CHECK (ordinal > 0 AND amount > 0 AND base_amount > 0 AND document_count >= 0),
    CONSTRAINT ck_financial_opening_entry_fin_open_entry_side CHECK (side IN ('DEBIT','CREDIT')),
    CONSTRAINT uq_financial_opening_entry_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_financial_opening_entry_financial_opening_entry_version CHECK (row_version > 0),
    CONSTRAINT fk_financial_opening_entry_revision_id FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES financial_opening_revision (tenant_id, company_id, id),
    CONSTRAINT fk_financial_opening_entry_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
    CONSTRAINT fk_financial_opening_entry_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id)
,
KEY ix_fin_open_entry_account (tenant_id, company_id, revision_id, account_id, id),
KEY ix_fin_open_entry_party (tenant_id, company_id, revision_id, party_id, id),
KEY ix_fin_open_entry_revision (tenant_id, company_id, revision_id, id),
KEY ix_financial_opening_entry_page (tenant_id, company_id, id),
KEY ix_financial_opening_entry_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM financial_opening_entry LIMIT 1")).first():
        raise RuntimeError("archive financial opening evidence before downgrade")
    op.execute("DROP TABLE financial_opening_entry")
