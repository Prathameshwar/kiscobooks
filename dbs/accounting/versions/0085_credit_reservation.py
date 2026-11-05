"""credit_reservation; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE credit_reservation (
	account_id BINARY(16) NOT NULL,
	party_id BINARY(16) NOT NULL,
	`role` VARCHAR(20) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	amount NUMERIC(19, 4) NOT NULL,
	base_currency VARCHAR(3) NOT NULL,
	base_amount NUMERIC(19, 4) NOT NULL,
	source_system VARCHAR(40) NOT NULL,
	source_type VARCHAR(40) NOT NULL,
	source_id VARCHAR(120) NOT NULL,
	status VARCHAR(20) NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	journal_id BINARY(16),
	override_id BINARY(16),
	decision JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_credit_reservation PRIMARY KEY (id),
	CONSTRAINT ck_credit_reservation_credit_reservation_status CHECK (status IN ('ACTIVE', 'CONSUMED', 'RELEASED')),
	CONSTRAINT ck_credit_reservation_credit_reservation_amount CHECK (amount > 0 AND base_amount > 0),
	CONSTRAINT ck_credit_reservation_credit_reservation_role CHECK (role IN ('CUSTOMER', 'SUPPLIER')),
	CONSTRAINT uq_credit_reservation_source UNIQUE (tenant_id, company_id, source_system, source_type, source_id),
	CONSTRAINT uq_credit_reservation_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_credit_reservation_credit_reservation_version CHECK (row_version > 0),
	CONSTRAINT fk_credit_reservation_account_id FOREIGN KEY(tenant_id, company_id, account_id) REFERENCES account (tenant_id, company_id, id),
	CONSTRAINT fk_credit_reservation_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
	CONSTRAINT fk_credit_reservation_journal_id FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT fk_credit_reservation_override_id FOREIGN KEY(tenant_id, company_id, override_id) REFERENCES credit_override (tenant_id, company_id, id),
	INDEX ix_credit_reservation_exposure (tenant_id, company_id, party_id, `role`, status, expires_at, id),
	INDEX ix_credit_reservation_page (tenant_id, company_id, id),
	INDEX ix_credit_reservation_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE credit_reservation"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
