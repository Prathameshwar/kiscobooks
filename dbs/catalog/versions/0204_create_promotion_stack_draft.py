"""Create native promotion-stack draft storage; one reversible DDL."""
from alembic import op

revision = "0204"
down_revision = "0203"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_stack_draft (
	code VARCHAR(30) NOT NULL, 
	maximum_applied INTEGER NOT NULL, 
	change_reason VARCHAR(500) NOT NULL, 
	row_version INTEGER NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	group_count INTEGER NOT NULL, 
	permission_count INTEGER NOT NULL, 
	published_policy_id BINARY(16) NULL,
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_stack_draft PRIMARY KEY (id), 
	CONSTRAINT uq_promotion_stack_draft_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_promotion_stack_draft_bounds CHECK (row_version >= 1 AND maximum_applied BETWEEN 1 AND 10), 
	CONSTRAINT ck_promotion_stack_draft_status CHECK (status IN ('DRAFT','PUBLISHED')), 
	CONSTRAINT ck_promotion_stack_draft_counts CHECK (group_count BETWEEN 0 AND 20 AND permission_count BETWEEN 0 AND 190), 
	CONSTRAINT ck_promotion_stack_draft_publication CHECK ((status = 'DRAFT' AND published_policy_id IS NULL) OR (status = 'PUBLISHED' AND published_policy_id IS NOT NULL)), 
	CONSTRAINT fk_stack_draft_publication FOREIGN KEY(tenant_id, company_id, published_policy_id) REFERENCES promotion_stack_policy (tenant_id, company_id, id),
	KEY ix_promotion_stack_draft_code (tenant_id, company_id, code, id),
	KEY ix_promotion_stack_draft_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE promotion_stack_draft")
