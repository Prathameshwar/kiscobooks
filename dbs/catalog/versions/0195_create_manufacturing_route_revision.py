"""Create sequential route definitions; one reversible DDL."""
from alembic import op

revision = "0195"
down_revision = "0194"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE manufacturing_route_revision (
	company_id BINARY(16) NOT NULL, 
	route_id BINARY(16) NOT NULL, 
	revision INTEGER NOT NULL, 
	row_version INTEGER NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	published_at DATETIME(6) NULL,
	specification VARCHAR(2000) NOT NULL, 
	change_reason VARCHAR(500) NOT NULL, 
	step_count INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_manufacturing_route_revision PRIMARY KEY (id), 
	CONSTRAINT uq_manufacturing_route_rev_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_manufacturing_route_rev_number UNIQUE (tenant_id, company_id, route_id, revision), 
	CONSTRAINT fk_manufacturing_route_rev_parent FOREIGN KEY(tenant_id, company_id, route_id) REFERENCES manufacturing_route (tenant_id, company_id, id), 
	CONSTRAINT ck_manufacturing_route_revision_route_rev_numbers CHECK (revision >= 1 AND row_version >= 1 AND step_count BETWEEN 0 AND 50), 
	CONSTRAINT ck_manufacturing_route_revision_route_rev_status CHECK (status IN ('DRAFT','PUBLISHED','RETIRED') AND ((status = 'DRAFT' AND published_at IS NULL) OR (status IN ('PUBLISHED','RETIRED') AND published_at IS NOT NULL))),
	KEY ix_manufacturing_route_rev_published (tenant_id, company_id, route_id, published_at, revision, id),
	KEY ix_manufacturing_route_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE manufacturing_route_revision")
