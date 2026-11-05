"""Create native promotion-stack draft storage; one reversible DDL."""
from alembic import op

revision = "0205"
down_revision = "0204"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE promotion_stack_draft_group (
	draft_id BINARY(16) NOT NULL, 
	position INTEGER NOT NULL, 
	stage VARCHAR(20) NOT NULL, 
	selection VARCHAR(20) NOT NULL, 
	changes_basket BOOL NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_promotion_stack_draft_group PRIMARY KEY (id), 
	CONSTRAINT uq_promotion_stack_draft_group_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT uq_stack_draft_group_parent UNIQUE (tenant_id, company_id, draft_id, id), 
	CONSTRAINT uq_stack_draft_group_position UNIQUE (tenant_id, company_id, draft_id, position), 
	CONSTRAINT fk_stack_draft_group_parent FOREIGN KEY(tenant_id, company_id, draft_id) REFERENCES promotion_stack_draft (tenant_id, company_id, id), 
	CONSTRAINT ck_promotion_stack_draft_group_position CHECK (position BETWEEN 0 AND 19), 
	CONSTRAINT ck_promotion_stack_draft_group_stage CHECK (stage IN ('PRODUCT_SCHEME','BASKET','MANUAL')), 
	CONSTRAINT ck_promotion_stack_draft_group_selection CHECK (selection IN ('PRIORITY','BEST_SINGLE','CUSTOMER_CHOICE')), 
	CONSTRAINT ck_promotion_stack_draft_group_comparable CHECK (NOT (changes_basket = 1 AND selection = 'BEST_SINGLE')),
	KEY ix_promotion_stack_draft_group_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE promotion_stack_draft_group")
