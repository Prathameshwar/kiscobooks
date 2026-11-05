"""Create native BOM definitions; one reversible DDL."""
from alembic import op

revision = "0201"
down_revision = "0200"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE bom_component (
	quantity DECIMAL(19,4) NOT NULL, 
	basis VARCHAR(16) NOT NULL, 
	loss_fraction DECIMAL(19,8) NOT NULL, 
	timing VARCHAR(12) NOT NULL, 
	route_step_id BINARY(16) NULL,
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
	CONSTRAINT pk_bom_component PRIMARY KEY (id), 
	CONSTRAINT uq_bom_component_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_bom_component_draft_id_line_key UNIQUE (tenant_id, company_id, draft_id, line_key), 
	CONSTRAINT uq_bom_component_draft_id_sequence UNIQUE (tenant_id, company_id, draft_id, sequence), 
	CONSTRAINT uq_bom_component_revision_id_line_key UNIQUE (tenant_id, company_id, revision_id, line_key), 
	CONSTRAINT uq_bom_component_revision_id_sequence UNIQUE (tenant_id, company_id, revision_id, sequence), 
	CONSTRAINT fk_bom_component_draft FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES bom_draft (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_component_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES bom_revision (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_component_item FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id), 
	CONSTRAINT fk_bom_component_unit FOREIGN KEY(tenant_id, company_id, unit_revision_id) REFERENCES item_unit_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_component_bom_component_parent CHECK ((draft_id IS NOT NULL AND revision_id IS NULL) OR (draft_id IS NULL AND revision_id IS NOT NULL AND unit_revision_id IS NOT NULL)), 
	CONSTRAINT ck_bom_component_bom_component_sequence CHECK (sequence BETWEEN 1 AND 1000), 
	CONSTRAINT fk_bom_component_step FOREIGN KEY(tenant_id, company_id, route_step_id) REFERENCES manufacturing_route_step (tenant_id, company_id, id), 
	CONSTRAINT ck_bom_component_bom_component_quantity CHECK (quantity > 0 AND loss_fraction >= 0 AND loss_fraction < 1), 
	CONSTRAINT ck_bom_component_bom_component_basis CHECK (basis IN ('GROSS_INPUT','NET_REQUIRED') AND timing IN ('PER_BASIS','PER_RUN')), 
	CONSTRAINT ck_bom_component_bom_component_loss CHECK (basis = 'NET_REQUIRED' OR loss_fraction = 0),
	KEY ix_bom_component_item (tenant_id, company_id, item_id),
	KEY ix_bom_component_step (tenant_id, company_id, route_step_id),
	KEY ix_bom_component_tenant_id (tenant_id),
	KEY ix_bom_component_unit (tenant_id, company_id, unit_revision_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE bom_component")
