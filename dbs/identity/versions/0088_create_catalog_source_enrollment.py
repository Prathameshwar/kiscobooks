"""Create explicit Catalog source enrollments; one reversible DDL."""
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_source_enrollment (
	company_id BINARY(16) NOT NULL, 
	is_active BOOL NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_catalog_source_enrollment PRIMARY KEY (id), 
	CONSTRAINT uq_catalog_enrollment_company UNIQUE (tenant_id, company_id), 
	CONSTRAINT fk_catalog_enrollment_company FOREIGN KEY(tenant_id, company_id) REFERENCES company (tenant_id, id),
	KEY ix_catalog_enrollment_discovery (is_active, id),
	KEY ix_catalog_source_enrollment_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE catalog_source_enrollment")
