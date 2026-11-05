"""Immutable journal-line quote usage evidence; one DDL statement."""

from alembic import op

revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE exchange_rate_usage (
    journal_line_id BINARY(16) NOT NULL,
    quote_id BINARY(16) NOT NULL,
    purpose VARCHAR(20) NOT NULL,
    effective_date DATE NOT NULL,
    rate NUMERIC(27,12) NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_exchange_rate_usage PRIMARY KEY (id),
    CONSTRAINT uq_exchange_rate_usage_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_exchange_rate_usage_line UNIQUE (tenant_id, company_id, journal_line_id),
    CONSTRAINT fk_exchange_rate_usage_line FOREIGN KEY (tenant_id, company_id, journal_line_id)
        REFERENCES journal_line (tenant_id, company_id, id),
    CONSTRAINT fk_exchange_rate_usage_quote FOREIGN KEY (tenant_id, company_id, quote_id)
        REFERENCES exchange_rate_quote (tenant_id, company_id, id),
    CONSTRAINT ck_exchange_rate_usage_positive CHECK (rate > 0),
    KEY ix_exchange_rate_usage_quote (tenant_id, company_id, quote_id, id),
    KEY ix_exchange_rate_usage_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE exchange_rate_usage")
