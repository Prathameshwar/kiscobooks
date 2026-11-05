"""Create native promotion-stack draft storage; one reversible DDL."""
from alembic import op

revision = "0206"
down_revision = "0205"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_stack_draft_permission (
	draft_id BINARY(16) NOT NULL, 
	earlier_group_id BINARY(16) NOT NULL, 
	later_group_id BINARY(16) NOT NULL, 
	include_reward_units BOOL NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_stack_draft_permission PRIMARY KEY (id), 
	CONSTRAINT uq_promotion_stack_draft_permission_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT fk_stack_draft_permission_parent FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES promotion_stack_draft (tenant_id, company_id, id), 
	CONSTRAINT uq_stack_draft_permission_pair UNIQUE (tenant_id, company_id, draft_id, earlier_group_id, later_group_id), 
	CONSTRAINT fk_stack_draft_permission_earlier FOREIGN KEY(tenant_id, company_id, draft_id, earlier_group_id) REFERENCES promotion_stack_draft_group (tenant_id, company_id, draft_id, id), 
	CONSTRAINT fk_stack_draft_permission_later FOREIGN KEY(tenant_id, company_id, draft_id, later_group_id) REFERENCES promotion_stack_draft_group (tenant_id, company_id, draft_id, id), 
	CONSTRAINT ck_promotion_stack_draft_permission_distinct CHECK (earlier_group_id <> later_group_id),
	KEY ix_promotion_stack_draft_permission_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE promotion_stack_draft_permission")
