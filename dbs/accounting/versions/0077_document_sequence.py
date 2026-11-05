"""document_sequence; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE document_sequence (
	fiscal_year_id BINARY(16) NOT NULL,
	series_key VARCHAR(30) NOT NULL,
	next_value BIGINT NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_document_sequence PRIMARY KEY (id),
	CONSTRAINT uq_document_sequence_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_document_sequence_series UNIQUE (tenant_id, company_id, fiscal_year_id, series_key),
	CONSTRAINT fk_document_sequence_year FOREIGN KEY(tenant_id, company_id, fiscal_year_id) REFERENCES fiscal_year (tenant_id, company_id, id),
	CONSTRAINT ck_document_sequence_document_sequence_next CHECK (next_value >= 1 AND next_value <= 999999999),
	CONSTRAINT ck_document_sequence_document_sequence_version CHECK (row_version > 0),
	INDEX ix_document_sequence_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE document_sequence"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
