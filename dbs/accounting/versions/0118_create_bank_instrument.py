"""bank_instrument; one atomic CREATE with scoped ownership."""
from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE bank_instrument (
    intent_id BINARY(16),
    journal_line_id BINARY(16) NOT NULL,
    account_id BINARY(16) NOT NULL,
    tender_key BINARY(16) NOT NULL,
    mode VARCHAR(20) NOT NULL,
    reference VARCHAR(120),
    instrument_date DATE,
    booking_date DATE NOT NULL,
    recognition VARCHAR(20) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_bank_instrument PRIMARY KEY (id),
    CONSTRAINT uq_bank_instrument_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_bank_instrument_tenant_id_company_id_intent_id_tender_key UNIQUE (tenant_id, company_id, intent_id, tender_key),
    CONSTRAINT fk_bank_instrument_intent FOREIGN KEY(tenant_id, company_id, intent_id) REFERENCES voucher_money_intent (tenant_id, company_id, id),
    CONSTRAINT fk_bank_instrument_line FOREIGN KEY(tenant_id, company_id, journal_line_id) REFERENCES journal_line (tenant_id, company_id, id),
    CONSTRAINT fk_bank_instrument_account FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
    CONSTRAINT ck_bank_instrument_bank_instrument_positive CHECK (amount > 0),
    INDEX ix_bank_instrument_book (tenant_id, company_id, account_id, booking_date, id),
    INDEX ix_bank_instrument_page (tenant_id, company_id, id),
    INDEX ix_bank_instrument_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_instrument")
