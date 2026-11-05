"""Create native promotion-limit definition storage; one reversible DDL."""
from alembic import op

revision = "0208"
down_revision = "0207"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_limit_revision (
	definition_id BINARY(16) NOT NULL, 
	maximum_count BIGINT NULL,
	maximum_quantity DECIMAL(19,4) NULL,
	maximum_amount DECIMAL(19,4) NULL,
	company_id BINARY(16) NOT NULL, 
	revision INTEGER NOT NULL, 
	row_version INTEGER NOT NULL, 
	published_at DATETIME(6) NULL,
	published_source_version BIGINT NULL,
	publication_generation BIGINT NULL,
	change_reason VARCHAR(500) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_limit_revision PRIMARY KEY (id), 
	CONSTRAINT uq_promotion_limit_revision_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_limit_revision_parent_scope UNIQUE (tenant_id, company_id, definition_id, id), 
	CONSTRAINT uq_promotion_limit_revision_number UNIQUE (tenant_id, company_id, definition_id, revision), 
	CONSTRAINT fk_promotion_limit_revision_parent FOREIGN KEY(tenant_id, company_id, definition_id) REFERENCES promotion_limit_definition (tenant_id, company_id, id), 
	CONSTRAINT ck_promotion_limit_revision_version CHECK (revision >= 1 AND row_version >= 1), 
	CONSTRAINT ck_promotion_limit_revision_publication CHECK ((published_at IS NULL AND published_source_version IS NULL AND publication_generation IS NULL) OR (published_at IS NOT NULL AND published_source_version IS NOT NULL AND publication_generation IS NOT NULL AND published_source_version >= 1 AND publication_generation >= 1)), 
	CONSTRAINT ck_promotion_limit_revision_cap CHECK ((maximum_count IS NOT NULL AND maximum_count > 0 AND maximum_quantity IS NULL AND maximum_amount IS NULL) OR (maximum_count IS NULL AND maximum_quantity IS NOT NULL AND maximum_quantity > 0 AND maximum_amount IS NULL) OR (maximum_count IS NULL AND maximum_quantity IS NULL AND maximum_amount IS NOT NULL AND maximum_amount > 0)),
	KEY ix_promotion_limit_revision_published (tenant_id, company_id, definition_id, published_at, revision, id),
	KEY ix_promotion_limit_revision_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE promotion_limit_revision")
