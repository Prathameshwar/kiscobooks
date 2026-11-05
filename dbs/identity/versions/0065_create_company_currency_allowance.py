"""Company-approved foreign transaction currencies."""

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE company_currency_allowance (
    company_id BINARY(16) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_company_currency_allowance PRIMARY KEY (id),
    CONSTRAINT uq_company_currency_allowance_tenant_id_company_id_id
        UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_company_currency_allowance_tenant_id_company_id_currency_code
        UNIQUE (tenant_id, company_id, currency_code),
    CONSTRAINT fk_company_currency_allowance_company FOREIGN KEY (tenant_id, company_id)
        REFERENCES company (tenant_id, id),
    CONSTRAINT fk_company_currency_allowance_currency FOREIGN KEY (currency_code)
        REFERENCES currency (code),
    KEY ix_company_currency_allowance_company_active (tenant_id, company_id, is_active),
    KEY ix_company_currency_allowance_tenant_id (tenant_id)
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE=utf8mb4_unicode_ci
""")


def downgrade() -> None:
    op.execute("DROP TABLE company_currency_allowance")
