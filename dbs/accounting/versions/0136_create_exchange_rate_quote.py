"""Purpose-specific reviewed FX quote book; one DDL statement."""

from alembic import op

revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE exchange_rate_quote (
    from_currency VARCHAR(3) NOT NULL,
    to_currency VARCHAR(3) NOT NULL,
    purpose VARCHAR(20) NOT NULL,
    effective_date DATE NOT NULL,
    rate NUMERIC(27,12) NOT NULL,
    source_kind VARCHAR(12) NOT NULL,
    source_reference VARCHAR(500) NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(12) NOT NULL,
    approved_slot INTEGER GENERATED ALWAYS AS
        (CASE WHEN status = 'APPROVED' THEN 1 ELSE NULL END) STORED,
    approved_at DATETIME(6) NULL,
    approved_by BINARY(16) NULL,
    approval_reason VARCHAR(500) NULL,
    withdrawn_at DATETIME(6) NULL,
    withdrawn_by BINARY(16) NULL,
    withdrawal_reason VARCHAR(500) NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_exchange_rate_quote PRIMARY KEY (id),
    CONSTRAINT uq_exchange_rate_quote_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_exchange_rate_quote_approved UNIQUE
        (tenant_id, company_id, from_currency, to_currency, purpose, effective_date, approved_slot),
    CONSTRAINT ck_exchange_rate_quote_positive CHECK (rate > 0),
    CONSTRAINT ck_exchange_rate_quote_pair CHECK (from_currency <> to_currency),
    CONSTRAINT ck_exchange_rate_quote_purpose CHECK
        (purpose IN ('ACCOUNTING','GST_GOODS','GST_SERVICES','REVALUATION','SETTLEMENT')),
    CONSTRAINT ck_exchange_rate_quote_source CHECK (source_kind IN ('MANUAL','CSV','CUSTOMS')),
    CONSTRAINT ck_exchange_rate_quote_status CHECK
        (status IN ('CANDIDATE','APPROVED','WITHDRAWN')),
    CONSTRAINT ck_exchange_rate_quote_version CHECK (row_version > 0),
    KEY ix_exchange_rate_quote_asof
        (tenant_id, company_id, from_currency, to_currency, purpose, effective_date, status, id),
    KEY ix_exchange_rate_quote_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE exchange_rate_quote")
