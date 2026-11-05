"""Create native BOM definitions; one reversible DDL."""
from alembic import op

revision = "0198"
down_revision = "0197"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bom_draft (
	draft_number INTEGER NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	published_revision_id BINARY(16) NULL,
	company_id BINARY(16) NOT NULL, 
	bom_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	specification VARCHAR(2000) NOT NULL, 
	change_reason VARCHAR(500) NOT NULL, 
	definition_date DATE NOT NULL, 
	route_revision_id BINARY(16) NULL,
	batch_minimum DECIMAL(19,4) NULL,
	batch_maximum DECIMAL(19,4) NULL,
	batch_multiple DECIMAL(19,4) NULL,
	component_count INTEGER NOT NULL, 
	output_count INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_bom_draft PRIMARY KEY (id), 
	CONSTRAINT uq_bom_draft_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_draft_bom_draft_version CHECK (row_version >= 1), 
	CONSTRAINT fk_bom_draft_bom FOREIGN KEY(tenant_id, company_id, bom_id) REFERENCES bom (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_draft_route FOREIGN KEY(tenant_id, company_id, route_revision_id) REFERENCES manufacturing_route_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_draft_bom_draft_date CHECK (definition_date >= '1000-01-01'), 
	CONSTRAINT ck_bom_draft_bom_draft_counts CHECK (component_count BETWEEN 0 AND 1000 AND output_count BETWEEN 0 AND 100), 
	CONSTRAINT ck_bom_draft_bom_draft_batch CHECK ((batch_minimum IS NULL OR batch_minimum > 0) AND (batch_maximum IS NULL OR batch_maximum > 0) AND (batch_multiple IS NULL OR batch_multiple > 0) AND (batch_minimum IS NULL OR batch_maximum IS NULL OR batch_minimum <= batch_maximum)), 
	CONSTRAINT uq_bom_draft_number UNIQUE (tenant_id, company_id, bom_id, draft_number), 
	CONSTRAINT ck_bom_draft_bom_draft_number CHECK (draft_number >= 1), 
	CONSTRAINT ck_bom_draft_bom_draft_status CHECK ((status = 'DRAFT' AND published_revision_id IS NULL) OR (status = 'PUBLISHED' AND published_revision_id IS NOT NULL)),
	KEY ix_bom_draft_route (tenant_id, company_id, route_revision_id),
	KEY ix_bom_draft_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bom_draft")
