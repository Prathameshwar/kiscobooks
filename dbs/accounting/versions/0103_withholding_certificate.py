"""withholding_certificate; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE withholding_certificate (
	party_id BINARY(16) NOT NULL,
	section_id BINARY(16) NOT NULL,
	certificate_reference VARCHAR(80) NOT NULL,
	rate_percent NUMERIC(19, 4) NOT NULL,
	amount_limit NUMERIC(19, 4),
	currency VARCHAR(3),
	source_reference VARCHAR(500) NOT NULL,
	source_url VARCHAR(1000) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_withholding_certificate PRIMARY KEY (id),
	CONSTRAINT uq_withholding_certificate_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_withholding_certificate_withholding_certificate_version CHECK (row_version > 0),
	CONSTRAINT fk_withholding_certificate_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
	CONSTRAINT fk_withholding_certificate_section_id FOREIGN KEY(tenant_id, company_id, section_id) REFERENCES withholding_section (tenant_id, company_id, id),
	CONSTRAINT ck_withholding_certificate_withholding_certificate_percent CHECK (rate_percent >= 0 AND rate_percent <= 100),
	CONSTRAINT ck_withholding_certificate_withholding_certificate_limit CHECK ((amount_limit IS NULL AND currency IS NULL) OR (amount_limit IS NOT NULL AND amount_limit > 0 AND currency IS NOT NULL)),
	CONSTRAINT ck_withholding_certificate_withholding_certificate_evidence CHECK (LENGTH(source_sha256) = 64),
	CONSTRAINT ck_withholding_certificate_withholding_certificate_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	INDEX ix_withholding_certificate_asof (tenant_id, company_id, valid_from, id),
	INDEX ix_withholding_certificate_page (tenant_id, company_id, id),
	INDEX ix_withholding_certificate_ref1 (tenant_id, company_id, section_id),
	INDEX ix_withholding_certificate_tenant_id (tenant_id),
	INDEX ix_withholding_certificate_term (tenant_id, company_id, party_id, section_id, valid_from)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE withholding_certificate"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
