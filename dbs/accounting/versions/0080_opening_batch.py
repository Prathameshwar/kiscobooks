"""opening_batch; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE opening_batch (
	status VARCHAR(20) NOT NULL,
	posting_date DATE NOT NULL,
	journal_id BINARY(16),
	replacement_of_id BINARY(16),
	description VARCHAR(1000) NOT NULL,
	payload JSON NOT NULL,
	finalized_at DATETIME(6),
	reversal_reason VARCHAR(500),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_opening_batch PRIMARY KEY (id),
	CONSTRAINT uq_opening_batch_journal UNIQUE (tenant_id, company_id, journal_id),
	CONSTRAINT ck_opening_batch_opening_batch_status CHECK (status IN ('DRAFT', 'FINALIZED', 'REVERSED', 'VOID')),
	CONSTRAINT uq_opening_batch_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_opening_batch_opening_batch_version CHECK (row_version > 0),
	CONSTRAINT fk_opening_batch_journal_id FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT fk_opening_batch_replacement_of_id FOREIGN KEY(tenant_id, company_id, replacement_of_id) REFERENCES opening_batch (tenant_id, company_id, id),
	INDEX ix_opening_batch_page (tenant_id, company_id, id),
	INDEX ix_opening_batch_status (tenant_id, company_id, status, id),
	INDEX ix_opening_batch_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE opening_batch"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
