"""Create manufacturing_operation_revision; one reversible DDL paired with its model."""

from alembic import op

revision = "0193"
down_revision = "0192"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE manufacturing_operation_revision (
	company_id BINARY(16) NOT NULL, 
	operation_id BINARY(16) NOT NULL, 
	revision INTEGER NOT NULL, 
	row_version INTEGER NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	published_at DATETIME(6) NULL, 
	specification VARCHAR(2000) NOT NULL, 
	change_reason VARCHAR(500) NOT NULL, 
	service_item_id BINARY(16) NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL, 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL, 
	CONSTRAINT pk_manufacturing_operation_revision PRIMARY KEY (id), 
	CONSTRAINT uq_manufacturing_op_rev_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_manufacturing_op_rev_number UNIQUE (tenant_id, company_id, operation_id, revision), 
	CONSTRAINT fk_manufacturing_op_rev_parent FOREIGN KEY(tenant_id, company_id, operation_id) REFERENCES manufacturing_operation (tenant_id, company_id, id), 
	CONSTRAINT fk_manufacturing_op_rev_service FOREIGN KEY(tenant_id, company_id, service_item_id) REFERENCES item (tenant_id, company_id, id), 
	CONSTRAINT ck_manufacturing_operation_revision_manufacturing_op_rev_version CHECK (revision >= 1 AND row_version >= 1), 
	CONSTRAINT ck_manufacturing_operation_revision_manufacturing_op_rev_status CHECK (status IN ('DRAFT','PUBLISHED','RETIRED') AND ((status = 'DRAFT' AND published_at IS NULL) OR (status IN ('PUBLISHED','RETIRED') AND published_at IS NOT NULL))),
	KEY ix_manufacturing_op_rev_published (tenant_id, company_id, operation_id, published_at, revision, id),
	KEY ix_manufacturing_operation_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE manufacturing_operation_revision")
