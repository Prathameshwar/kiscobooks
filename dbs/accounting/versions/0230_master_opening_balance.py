"""master_opening_balance: one atomic CREATE TABLE, no financial postings."""
from alembic import op
from sqlalchemy import text

revision = "0230"
down_revision = "0229"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE master_opening_balance (
    account_id BINARY(16) NOT NULL,
    source_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    opening_date DATE NOT NULL,
    entry JSON NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_master_opening_balance PRIMARY KEY (id),
    CONSTRAINT uq_master_opening_balance_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_master_opening_account UNIQUE (tenant_id, company_id, account_id),
    CONSTRAINT uq_master_opening_source UNIQUE (tenant_id, company_id, source_key),
    CONSTRAINT ck_master_opening_balance_master_opening_status CHECK (status IN ('PENDING', 'WITHDRAWN')),
    CONSTRAINT ck_master_opening_balance_master_opening_balance_version CHECK (row_version > 0),
    CONSTRAINT fk_master_opening_balance_account_id FOREIGN KEY (tenant_id, company_id, account_id)
      REFERENCES account (tenant_id, company_id, id),
    KEY ix_master_opening_status (tenant_id, company_id, status, id),
    KEY ix_master_opening_balance_page (tenant_id, company_id, id),
    KEY ix_master_opening_balance_tenant_id (tenant_id)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM master_opening_balance LIMIT 1")).first():
        raise RuntimeError("archive held master openings before downgrade")
    op.execute("DROP TABLE master_opening_balance")
