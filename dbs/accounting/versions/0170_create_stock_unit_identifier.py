"""Prepared tracking identity: stock_unit_identifier; one reversible DDL."""
from alembic import op

revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_unit_identifier (
	unit_id BINARY(16) NOT NULL, 
	identifier_type VARCHAR(10) NOT NULL, 
	namespace_key VARCHAR(40) NOT NULL, 
	slot INTEGER NOT NULL, 
	value VARCHAR(120) NOT NULL, 
	normalized_value VARCHAR(120) COLLATE utf8mb4_bin NOT NULL, 
	normalization_version INTEGER NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_unit_identifier PRIMARY KEY (id), 
	CONSTRAINT uq_stock_unit_identifier_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_unit_identifier_stock_unit_identifier_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_unit_identifier_identity UNIQUE (tenant_id, company_id, identifier_type, namespace_key, normalized_value), 
	CONSTRAINT uq_stock_unit_identifier_slot UNIQUE (tenant_id, company_id, unit_id, identifier_type, slot), 
	CONSTRAINT ck_stock_unit_identifier_stock_unit_identifier_type CHECK (identifier_type IN ('SERIAL','IMEI')), 
	CONSTRAINT ck_stock_unit_identifier_stock_unit_identifier_bounds CHECK (slot BETWEEN 1 AND 8 AND normalization_version = 1), 
	CONSTRAINT fk_stock_unit_identifier_unit FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES stock_unit (tenant_id, company_id, id),
	KEY ix_stock_unit_identifier_lookup (tenant_id, company_id, normalized_value, id),
	KEY ix_stock_unit_identifier_page (tenant_id, company_id, id),
	KEY ix_stock_unit_identifier_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_unit_identifier")
