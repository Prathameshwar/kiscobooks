"""Create native BOM definitions; one reversible DDL."""
from alembic import op

revision = "0203"
down_revision = "0202"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bom_assignment (
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	bom_revision_id BINARY(16) NOT NULL, 
	item_id BINARY(16) NOT NULL, 
	output_role VARCHAR(12) NOT NULL, 
	warehouse_id BINARY(16) NULL,
	scope_key VARCHAR(32) GENERATED ALWAYS AS (CASE WHEN warehouse_id IS NULL THEN '*' ELSE HEX(warehouse_id) END) STORED NOT NULL, 
	valid_from DATE NOT NULL, 
	valid_to DATE NULL,
	is_active BOOL NOT NULL, 
	active_slot INTEGER GENERATED ALWAYS AS (CASE WHEN is_active THEN 1 ELSE NULL END) STORED NULL,
	change_reason VARCHAR(500) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bom_assignment PRIMARY KEY (id), 
	CONSTRAINT uq_bom_assignment_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_assignment_bom_assignment_version CHECK (row_version >= 1), 
	CONSTRAINT fk_bom_assignment_revision FOREIGN KEY(tenant_id, company_id, bom_revision_id) REFERENCES bom_revision (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_assignment_item FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_assignment_warehouse FOREIGN KEY(tenant_id, company_id, warehouse_id) REFERENCES warehouse (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_assignment_primary FOREIGN KEY(tenant_id, company_id, bom_revision_id, item_id, output_role) REFERENCES bom_output (tenant_id, company_id, revision_id, item_id, `role`), 
	CONSTRAINT uq_bom_assignment_start UNIQUE (tenant_id, company_id, item_id, scope_key, valid_from, active_slot), 
	CONSTRAINT ck_bom_assignment_bom_assignment_output CHECK (output_role = 'PRIMARY'), 
	CONSTRAINT ck_bom_assignment_bom_assignment_dates CHECK (valid_from >= '1000-01-01' AND (valid_to IS NULL OR valid_to >= valid_from)),
	KEY ix_bom_assignment_resolve (tenant_id, company_id, item_id, scope_key, is_active, valid_from, id),
	KEY ix_bom_assignment_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bom_assignment")
