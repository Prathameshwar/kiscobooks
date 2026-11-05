"""Create tax_category; one reversible DDL."""
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_category (
	code VARCHAR(30) NOT NULL,
	name VARCHAR(100) NOT NULL,
	is_active BOOL NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_category PRIMARY KEY (id),
	CONSTRAINT uq_tax_category_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_category_version CHECK (row_version >= 1),
	CONSTRAINT uq_tax_category_code UNIQUE (tenant_id, company_id, code),
    INDEX ix_tax_category_name (tenant_id, company_id, name, id),
    INDEX ix_tax_category_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE tax_category")
