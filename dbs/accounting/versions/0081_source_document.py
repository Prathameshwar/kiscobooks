"""source_document; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE source_document (
	journal_id BINARY(16) NOT NULL,
	account_id BINARY(16) NOT NULL,
	party_id BINARY(16) NOT NULL,
	`role` VARCHAR(20) NOT NULL,
	status VARCHAR(20) NOT NULL,
	kind VARCHAR(30) NOT NULL,
	direction VARCHAR(10) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	posting_date DATE NOT NULL,
	reference VARCHAR(120) NOT NULL,
	payload JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_source_document PRIMARY KEY (id),
	CONSTRAINT uq_source_document_journal UNIQUE (tenant_id, company_id, journal_id),
	CONSTRAINT ck_source_document_source_document_status CHECK (status IN ('DRAFT', 'POSTED', 'REVERSED', 'VOID')),
	CONSTRAINT ck_source_document_source_document_direction CHECK (direction IN ('DEBT', 'CREDIT')),
	CONSTRAINT ck_source_document_source_document_role CHECK (role IN ('CUSTOMER', 'SUPPLIER')),
	CONSTRAINT ck_source_document_source_document_amount CHECK (amount > 0),
	CONSTRAINT uq_source_document_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_source_document_source_document_version CHECK (row_version > 0),
	CONSTRAINT fk_source_document_journal_id FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT fk_source_document_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT fk_source_document_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
	INDEX ix_source_document_page (tenant_id, company_id, id),
	INDEX ix_source_document_party (tenant_id, company_id, party_id, `role`, id),
	INDEX ix_source_document_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE source_document"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
