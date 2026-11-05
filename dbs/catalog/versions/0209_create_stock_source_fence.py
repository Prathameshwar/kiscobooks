"""Bounded authenticated Accounting stock definition lease; one reversible CREATE."""
from alembic import op

revision = "0209"
down_revision = "0208"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE stock_source_fence (
	company_id BINARY(16) NOT NULL, 
	execution_id BINARY(16) NOT NULL, 
	actor_user_id BINARY(16) NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	expires_at DATETIME(6) NOT NULL, 
	closed_at DATETIME(6), 
	facts JSON NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_source_fence PRIMARY KEY (id), 
	CONSTRAINT uq_stock_source_fence_execution UNIQUE (tenant_id, company_id, execution_id), 
	CONSTRAINT ck_stock_source_fence_stock_source_fence_lifetime CHECK (expires_at > created_at),
	KEY ix_stock_source_fence_live (tenant_id, company_id, closed_at, expires_at, id),
	KEY ix_stock_source_fence_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")

def downgrade() -> None:
    op.execute("DROP TABLE stock_source_fence")
