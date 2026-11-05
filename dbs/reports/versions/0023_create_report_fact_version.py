"""report_fact_version; one atomic CREATE, with scoped constraints."""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_fact_version (
	epoch_id BINARY(16) NOT NULL,
	bundle_id BINARY(16) NOT NULL,
	ordinal BIGINT NOT NULL,
	entity VARCHAR(40) NOT NULL,
	source_id BINARY(16) NOT NULL,
	valid_from_sequence BIGINT NOT NULL,
	valid_to_sequence BIGINT,
	content_hash VARCHAR(64) NOT NULL,
	data JSON,
	wire_bytes INTEGER NOT NULL,
	relation_id BINARY(16),
	origin_id BINARY(16),
	account_id BINARY(16),
	party_id BINARY(16),
	posting_date DATE,
	currency VARCHAR(3),
	base_currency VARCHAR(3),
	amount NUMERIC(19, 4),
	base_amount NUMERIC(19, 4),
	side VARCHAR(10),
	source_status VARCHAR(30),
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_fact_version PRIMARY KEY (id),
	CONSTRAINT uq_report_fact_version_source UNIQUE (tenant_id, company_id, epoch_id, entity, source_id, valid_from_sequence),
	CONSTRAINT uq_report_fact_version_ordinal UNIQUE (tenant_id, company_id, bundle_id, ordinal),
	CONSTRAINT ck_report_fact_version_report_fact_version_interval CHECK (valid_from_sequence >= 0 AND (valid_to_sequence IS NULL OR valid_to_sequence > valid_from_sequence) AND ordinal > 0),
	CONSTRAINT ck_report_fact_version_report_fact_version_bytes CHECK (wire_bytes > 0 AND wire_bytes <= 1048576),
	CONSTRAINT uq_report_fact_version_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_fact_version_epoch_id FOREIGN KEY(tenant_id, company_id, epoch_id) REFERENCES report_source_epoch (tenant_id, company_id, id),
	CONSTRAINT fk_report_fact_version_bundle_id FOREIGN KEY(tenant_id, company_id, bundle_id) REFERENCES report_bundle (tenant_id, company_id, id),
	INDEX ix_report_fact_version_added (tenant_id, company_id, epoch_id, valid_from_sequence, entity, source_id),
	INDEX ix_report_fact_version_closed (tenant_id, company_id, epoch_id, valid_to_sequence, valid_from_sequence),
	INDEX ix_report_fact_version_account (tenant_id, company_id, epoch_id, entity, account_id, source_id, valid_from_sequence),
	INDEX ix_report_fact_version_date (tenant_id, company_id, epoch_id, entity, posting_date, source_id, valid_from_sequence),
	INDEX ix_report_fact_version_page (tenant_id, company_id, id),
	INDEX ix_report_fact_version_origin (tenant_id, company_id, epoch_id, entity, origin_id, source_id, valid_from_sequence),
	INDEX ix_report_fact_version_relation (tenant_id, company_id, epoch_id, entity, relation_id, source_id, valid_from_sequence),
	INDEX ix_report_fact_version_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE report_fact_version")
