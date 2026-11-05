"""Prepared tracking identity: stock_tracking_event; one reversible DDL."""
from alembic import op

revision = "0171"
down_revision = "0170"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_tracking_event (
	target_id BINARY(16) NOT NULL, 
	resource VARCHAR(10) NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	evidence JSON NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_tracking_event PRIMARY KEY (id), 
	CONSTRAINT uq_stock_tracking_event_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_tracking_event_stock_tracking_event_version CHECK (row_version > 0), 
	CONSTRAINT ck_stock_tracking_event_stock_tracking_event_resource CHECK (resource IN ('BATCH','SERIAL')), 
	CONSTRAINT ck_stock_tracking_event_stock_tracking_event_action CHECK (action IN ('PREPARE','CORRECT','HOLD','RELEASE','RETIRE','REACTIVATE')),
	KEY ix_stock_tracking_event_page (tenant_id, company_id, id),
	KEY ix_stock_tracking_event_target (tenant_id, company_id, target_id, id),
	KEY ix_stock_tracking_event_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    op.execute("DROP TABLE stock_tracking_event")
