"""Create bank_statement_mapping as one DDL statement."""

from alembic import op

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bank_statement_mapping (
	account_id BINARY(16) NOT NULL,
	revision INTEGER NOT NULL,
	currency VARCHAR(3) NOT NULL,
	columns JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_bank_statement_mapping PRIMARY KEY (id),
	CONSTRAINT uq_bs_mapping_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_bs_mapping_account FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT uq_bs_mapping_revision UNIQUE (tenant_id, company_id, account_id, revision)
,
	KEY ix_bank_statement_mapping_tenant_id (tenant_id),
	KEY ix_statement_mapping_account (tenant_id, company_id, account_id, revision)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bank_statement_mapping")
