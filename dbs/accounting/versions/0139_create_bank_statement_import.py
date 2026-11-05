"""Create bank_statement_import as one DDL statement."""

from alembic import op

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_statement_import (
	account_id BINARY(16) NOT NULL,
	mapping_id BINARY(16) NOT NULL,
	file_sha256 VARCHAR(64) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	period_from DATE NOT NULL,
	period_to DATE NOT NULL,
	opening_balance NUMERIC(19, 4) NOT NULL,
	closing_balance NUMERIC(19, 4) NOT NULL,
	row_count INTEGER NOT NULL,
	status VARCHAR(12) NOT NULL,
	review_reason VARCHAR(500),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_statement_import PRIMARY KEY (id),
	CONSTRAINT uq_bs_import_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bs_import_account FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT fk_bs_import_mapping FOREIGN KEY(tenant_id, company_id, mapping_id) REFERENCES bank_statement_mapping (tenant_id, company_id, id),
	CONSTRAINT uq_bs_import_file UNIQUE (tenant_id, company_id, account_id, file_sha256),
	CONSTRAINT ck_bank_statement_import_statement_import_status CHECK (status IN ('PREVIEW','COMMITTED','REJECTED'))
,
	KEY ix_bank_statement_import_tenant_id (tenant_id),
	KEY ix_statement_import_account (tenant_id, company_id, account_id, id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_statement_import")
