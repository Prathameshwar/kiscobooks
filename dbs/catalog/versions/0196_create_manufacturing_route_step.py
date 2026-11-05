"""Create sequential route definitions; one reversible DDL."""
from alembic import op

revision = "0196"
down_revision = "0195"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE manufacturing_route_step (
	company_id BINARY(16) NOT NULL, 
	revision_id BINARY(16) NOT NULL, 
	sequence INTEGER NOT NULL, 
	operation_revision_id BINARY(16) NOT NULL, 
	setup_minutes DECIMAL(19,4) NOT NULL, 
	run_minutes DECIMAL(19,4) NOT NULL, 
	lead_time_minutes DECIMAL(19,4) NOT NULL, 
	time_basis VARCHAR(20) NOT NULL, 
	quantity_basis DECIMAL(19,4) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_manufacturing_route_step PRIMARY KEY (id), 
	CONSTRAINT uq_manufacturing_route_step_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_manufacturing_route_step_sequence UNIQUE (tenant_id, company_id, revision_id, sequence), 
	CONSTRAINT fk_manufacturing_route_step_parent FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES manufacturing_route_revision (tenant_id, company_id, id), 
	CONSTRAINT fk_manufacturing_route_step_operation FOREIGN KEY(tenant_id, company_id, operation_revision_id) REFERENCES manufacturing_operation_revision (tenant_id, company_id, id), 
	CONSTRAINT ck_manufacturing_route_step_route_step_sequence CHECK (sequence BETWEEN 1 AND 50), 
	CONSTRAINT ck_manufacturing_route_step_route_step_times CHECK (setup_minutes >= 0 AND run_minutes >= 0 AND lead_time_minutes >= 0 AND quantity_basis > 0), 
	CONSTRAINT ck_manufacturing_route_step_route_step_basis CHECK (time_basis IN ('PER_OUTPUT_UNIT','PER_BATCH')),
	KEY ix_manufacturing_route_step_operation (tenant_id, company_id, operation_revision_id),
	KEY ix_manufacturing_route_step_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE manufacturing_route_step")
