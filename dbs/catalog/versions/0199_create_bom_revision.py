"""Create native BOM definitions; one reversible DDL."""
from alembic import op

revision = "0199"
down_revision = "0198"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bom_revision (
	revision INTEGER NOT NULL, 
	draft_id BINARY(16) NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	published_at DATETIME(6) NOT NULL, 
	policy_generation BIGINT NOT NULL, 
	source_version BIGINT NOT NULL,
	content_sha256 VARCHAR(64) NOT NULL, 
	dependency_manifest JSON NOT NULL, 
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
	CONSTRAINT pk_bom_revision PRIMARY KEY (id), 
	CONSTRAINT uq_bom_revision_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_revision_bom_revision_version CHECK (row_version >= 1), 
	CONSTRAINT fk_bom_revision_bom FOREIGN KEY(tenant_id, company_id, bom_id) REFERENCES bom (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_revision_route FOREIGN KEY(tenant_id, company_id, route_revision_id) REFERENCES manufacturing_route_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_revision_bom_revision_date CHECK (definition_date >= '1000-01-01'), 
	CONSTRAINT ck_bom_revision_bom_revision_counts CHECK (component_count BETWEEN 0 AND 1000 AND output_count BETWEEN 0 AND 100), 
	CONSTRAINT ck_bom_revision_bom_revision_batch CHECK ((batch_minimum IS NULL OR batch_minimum > 0) AND (batch_maximum IS NULL OR batch_maximum > 0) AND (batch_multiple IS NULL OR batch_multiple > 0) AND (batch_minimum IS NULL OR batch_maximum IS NULL OR batch_minimum <= batch_maximum)), 
	CONSTRAINT uq_bom_revision_number UNIQUE (tenant_id, company_id, bom_id, revision), 
	CONSTRAINT uq_bom_revision_draft UNIQUE (tenant_id, company_id, draft_id), 
	CONSTRAINT fk_bom_revision_draft FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES bom_draft (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_revision_bom_revision_numbers CHECK (revision >= 1 AND policy_generation >= 1 AND source_version >= 1), 
	CONSTRAINT ck_bom_revision_bom_revision_status CHECK (status IN ('PUBLISHED','RETIRED')), 
	CONSTRAINT ck_bom_revision_bom_revision_outputs CHECK (output_count >= 1),
	KEY ix_bom_revision_published (tenant_id, company_id, bom_id, published_at, id),
	KEY ix_bom_revision_route (tenant_id, company_id, route_revision_id),
	KEY ix_bom_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bom_revision")
