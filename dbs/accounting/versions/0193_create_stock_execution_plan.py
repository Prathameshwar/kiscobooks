"""Immutable subordinate stock execution plan; one reversible CREATE."""
from alembic import op
from sqlalchemy import text

revision = "0193"
down_revision = "0192"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE stock_execution_plan (
	intent_id BINARY(16) NOT NULL, 
	execution_id BINARY(16) NOT NULL, 
	source_fence_id BINARY(16) NOT NULL, 
	source_fence_expires_at DATETIME(6) NOT NULL, 
	semantic_hash VARCHAR(64) NOT NULL, 
	source_facts JSON NOT NULL, 
	effects JSON NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_execution_plan PRIMARY KEY (id), 
	CONSTRAINT uq_stock_execution_plan_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_execution_plan_stock_execution_plan_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_execution_plan_intent FOREIGN KEY(tenant_id, company_id, intent_id) REFERENCES voucher_money_intent (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_execution_plan_intent UNIQUE (tenant_id, company_id, intent_id), 
	CONSTRAINT uq_stock_execution_plan_execution UNIQUE (tenant_id, company_id, execution_id), 
	CONSTRAINT uq_stock_execution_plan_fence UNIQUE (tenant_id, company_id, source_fence_id),
	KEY ix_stock_execution_plan_expiry (tenant_id, company_id, source_fence_expires_at, id),
	KEY ix_stock_execution_plan_page (tenant_id, company_id, id),
	KEY ix_stock_execution_plan_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT 1 FROM stock_execution_plan LIMIT 1")).first():
        raise RuntimeError("retained stock execution evidence requires a forward repair")
    op.execute("DROP TABLE stock_execution_plan")
