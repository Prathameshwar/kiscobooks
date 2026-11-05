"""credit_override; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE credit_override (
	account_id BINARY(16) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	source_system VARCHAR(40) NOT NULL,
	source_type VARCHAR(40) NOT NULL,
	source_id VARCHAR(120) NOT NULL,
	status VARCHAR(20) NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	approved_by BINARY(16),
	approved_at DATETIME(6),
	decision JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_credit_override PRIMARY KEY (id),
	CONSTRAINT ck_credit_override_credit_override_status CHECK (status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'USED')),
	CONSTRAINT ck_credit_override_credit_override_amount CHECK (amount > 0),
	CONSTRAINT uq_credit_override_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_credit_override_credit_override_version CHECK (row_version > 0),
	CONSTRAINT fk_credit_override_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	INDEX ix_credit_override_page (tenant_id, company_id, id),
	INDEX ix_credit_override_source (tenant_id, company_id, source_system, source_type, source_id, id),
	INDEX ix_credit_override_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE credit_override"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
