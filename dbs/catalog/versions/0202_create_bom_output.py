"""Create native BOM definitions; one reversible DDL."""
from alembic import op

revision = "0202"
down_revision = "0201"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bom_output (
	nominal_quantity DECIMAL(19,4) NOT NULL, 
	yield_fraction DECIMAL(19,8) NOT NULL, 
	`role` VARCHAR(12) NOT NULL, 
	primary_slot INTEGER GENERATED ALWAYS AS (CASE WHEN role = 'PRIMARY' THEN 1 ELSE NULL END) STORED NULL,
	company_id BINARY(16) NOT NULL, 
	draft_id BINARY(16) NULL,
	revision_id BINARY(16) NULL,
	line_key BINARY(16) NOT NULL, 
	sequence INTEGER NOT NULL, 
	item_id BINARY(16) NOT NULL, 
	unit_revision_id BINARY(16) NULL,
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bom_output PRIMARY KEY (id), 
	CONSTRAINT uq_bom_output_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_bom_output_draft_id_line_key UNIQUE (tenant_id, company_id, draft_id, line_key), 
	CONSTRAINT uq_bom_output_draft_id_sequence UNIQUE (tenant_id, company_id, draft_id, sequence), 
	CONSTRAINT uq_bom_output_revision_id_line_key UNIQUE (tenant_id, company_id, revision_id, line_key), 
	CONSTRAINT uq_bom_output_revision_id_sequence UNIQUE (tenant_id, company_id, revision_id, sequence), 
	CONSTRAINT fk_bom_output_draft FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES bom_draft (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_output_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES bom_revision (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_output_item FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_output_unit FOREIGN KEY(tenant_id, company_id, unit_revision_id) REFERENCES item_unit_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_output_bom_output_parent CHECK ((draft_id IS NOT NULL AND revision_id IS NULL) OR (draft_id IS NULL AND revision_id IS NOT NULL AND unit_revision_id IS NOT NULL)), 
	CONSTRAINT ck_bom_output_bom_output_sequence CHECK (sequence BETWEEN 1 AND 100), 
	CONSTRAINT uq_bom_output_draft_id_item_id UNIQUE (tenant_id, company_id, draft_id, item_id), 
	CONSTRAINT uq_bom_output_draft_id_primary_slot UNIQUE (tenant_id, company_id, draft_id, primary_slot), 
	CONSTRAINT uq_bom_output_revision_id_item_id UNIQUE (tenant_id, company_id, revision_id, item_id), 
	CONSTRAINT uq_bom_output_revision_id_primary_slot UNIQUE (tenant_id, company_id, revision_id, primary_slot), 
	CONSTRAINT uq_bom_output_assignment UNIQUE (tenant_id, company_id, revision_id, item_id, `role`), 
	CONSTRAINT ck_bom_output_bom_output_quantity CHECK (nominal_quantity > 0 AND yield_fraction > 0 AND yield_fraction <= 1), 
	CONSTRAINT ck_bom_output_bom_output_role CHECK (role IN ('PRIMARY','CO_PRODUCT','BY_PRODUCT','SCRAP')),
	KEY ix_bom_output_item (tenant_id, company_id, item_id),
	KEY ix_bom_output_tenant_id (tenant_id),
	KEY ix_bom_output_unit (tenant_id, company_id, unit_revision_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bom_output")
