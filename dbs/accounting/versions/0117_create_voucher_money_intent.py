"""voucher_money_intent; one atomic CREATE with scoped ownership."""
from alembic import op

revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE voucher_money_intent (
    execution_id BINARY(16) NOT NULL,
    voucher_id BINARY(16) NOT NULL,
    journal_id BINARY(16),
    request_hash VARCHAR(64) NOT NULL,
    kind VARCHAR(30) NOT NULL,
    posting_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    command JSON NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_voucher_money_intent PRIMARY KEY (id),
    CONSTRAINT uq_voucher_money_intent_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_voucher_money_intent_tenant_id_company_id_execution_id UNIQUE (tenant_id, company_id, execution_id),
    CONSTRAINT uq_voucher_money_intent_tenant_id_company_id_journal_id UNIQUE (tenant_id, company_id, journal_id),
    CONSTRAINT fk_money_intent_journal FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id),
    CONSTRAINT ck_voucher_money_intent_money_intent_status CHECK (status IN ('PREPARED', 'COMMITTED', 'CANCELLED')),
    INDEX ix_money_intent_source (tenant_id, company_id, voucher_id, status),
    INDEX ix_voucher_money_intent_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_money_intent")
