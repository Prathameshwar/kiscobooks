"""Create tax_classification; one reversible DDL."""
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_classification (
	jurisdiction VARCHAR(2) NOT NULL,
	code_system VARCHAR(3) NOT NULL,
	code VARCHAR(8) NOT NULL,
	item_kind VARCHAR(7) NOT NULL,
	description VARCHAR(1000) NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE NULL,
	source_reference VARCHAR(500) NOT NULL,
	source_url VARCHAR(1000) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_classification PRIMARY KEY (id),
	CONSTRAINT uq_tax_classification_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_classification_version CHECK (row_version >= 1),
	CONSTRAINT ck_tax_classification_start CHECK (valid_from >= '1000-01-01'),
	CONSTRAINT ck_tax_classification_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	CONSTRAINT uq_tax_classification_start UNIQUE (tenant_id, company_id, code_system, code, valid_from),
	CONSTRAINT ck_tax_classification_jurisdiction CHECK (jurisdiction = 'IN'),
	CONSTRAINT ck_tax_classification_kind CHECK ((code_system = 'HSN' AND item_kind = 'GOODS') OR (code_system = 'SAC' AND item_kind = 'SERVICE')),
    INDEX ix_tax_classification_code (tenant_id, company_id, code, id),
    INDEX ix_tax_classification_date (tenant_id, company_id, code_system, code, valid_from, id),
    INDEX ix_tax_classification_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE tax_classification")
