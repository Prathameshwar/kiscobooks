"""fiscal_status_transition; indexes and foreign keys created by one atomic DDL."""
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE fiscal_status_transition (
	period_id BINARY(16) NOT NULL,
	from_status VARCHAR(20) NOT NULL,
	to_status VARCHAR(20) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_fiscal_status_transition PRIMARY KEY (id),
	CONSTRAINT uq_fiscal_transition_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_fiscal_transition_period FOREIGN KEY(tenant_id, company_id, period_id) REFERENCES fiscal_period (tenant_id, company_id, id),
	CONSTRAINT ck_fiscal_status_transition_fiscal_transition_version CHECK (row_version > 0),
	CONSTRAINT ck_fiscal_status_transition_fiscal_transition_changed CHECK (from_status <> to_status),
	INDEX ix_fiscal_status_transition_tenant_id (tenant_id),
	INDEX ix_fiscal_transition_period (tenant_id, company_id, period_id, id)
)ROW_FORMAT=DYNAMIC ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE fiscal_status_transition"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
