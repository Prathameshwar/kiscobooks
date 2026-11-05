"""charge_tax_snapshot; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE charge_tax_snapshot (
	assessment_id BINARY(16) NOT NULL,
	provider_id BINARY(16) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	net_amount NUMERIC(19, 4) NOT NULL,
	gross_amount NUMERIC(19, 4) NOT NULL,
	input_hash VARCHAR(64) NOT NULL,
	key_id VARCHAR(120) NOT NULL,
	snapshot JSON NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_charge_tax_snapshot PRIMARY KEY (id),
	CONSTRAINT uq_charge_tax_assessment UNIQUE (tenant_id, company_id, assessment_id),
	CONSTRAINT uq_charge_tax_provider UNIQUE (tenant_id, company_id, provider_id),
	CONSTRAINT ck_charge_tax_snapshot_charge_tax_amount CHECK (net_amount > 0 AND gross_amount >= net_amount),
	CONSTRAINT uq_charge_tax_snapshot_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_charge_tax_snapshot_charge_tax_snapshot_version CHECK (row_version > 0),
	CONSTRAINT fk_charge_tax_snapshot_assessment_id FOREIGN KEY(tenant_id, company_id, assessment_id) REFERENCES charge_assessment (tenant_id, company_id, id),
	INDEX ix_charge_tax_snapshot_page (tenant_id, company_id, id),
	INDEX ix_charge_tax_snapshot_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE charge_tax_snapshot"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
