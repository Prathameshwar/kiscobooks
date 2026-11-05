"""tax_rate_replica: Catalog GST dated rate replica; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE tax_rate_replica (
	rule_id BINARY(16) NOT NULL,
	series_id BINARY(16) NOT NULL,
	applicability VARCHAR(12) NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE,
	supersedes_id BINARY(16),
	source_reference VARCHAR(500) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	source_version BIGINT NOT NULL,
	source_message_id BINARY(16) NOT NULL,
	replicated_at DATETIME(6) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	CONSTRAINT pk_tax_rate_replica PRIMARY KEY (id),
	CONSTRAINT uq_tax_rate_replica_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rate_replica_applicability CHECK (applicability IN ('INTRA_STATE','INTRA_UT','INTER_STATE')),
	CONSTRAINT ck_tax_rate_replica_source_version CHECK (source_version >= 1),
	CONSTRAINT ck_tax_rate_replica_dates CHECK (valid_from >= '1000-01-01' AND (valid_to IS NULL OR valid_to >= valid_from)),
	INDEX ix_tax_rate_replica_rule (tenant_id, company_id, rule_id, applicability, valid_from, id),
	INDEX ix_tax_rate_replica_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE tax_rate_replica"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
