"""party_withholding_profile; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE party_withholding_profile (
	party_id BINARY(16) NOT NULL,
	kind VARCHAR(10) NOT NULL,
	deductible BOOL NOT NULL,
	deductee_type VARCHAR(40) NOT NULL,
	pan_status VARCHAR(20) NOT NULL,
	pan_identifier_id BINARY(16),
	default_section_id BINARY(16),
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
	CONSTRAINT pk_party_withholding_profile PRIMARY KEY (id),
	CONSTRAINT uq_party_withholding_profile_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_party_withholding_profile_party_withholding_profile_version CHECK (row_version > 0),
	CONSTRAINT fk_party_withholding_profile_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
	CONSTRAINT fk_party_withholding_profile_pan_identifier_id FOREIGN KEY(tenant_id, company_id, pan_identifier_id) REFERENCES party_identifier (tenant_id, company_id, id),
	CONSTRAINT fk_party_withholding_profile_default_section_id FOREIGN KEY(tenant_id, company_id, default_section_id) REFERENCES withholding_section (tenant_id, company_id, id),
	CONSTRAINT ck_party_withholding_profile_party_withholding_profile_kind CHECK (kind IN ('TDS', 'TCS')),
	CONSTRAINT ck_party_withholding_profile_party_withholding_profile_d_b51e CHECK (deductee_type IN ('INDIVIDUAL', 'HUF', 'COMPANY', 'FIRM', 'AOP_BOI', 'LOCAL_AUTHORITY', 'ARTIFICIAL_JURIDICAL_PERSON', 'GOVERNMENT', 'COOPERATIVE', 'TRUST', 'NON_RESIDENT_COMPANY', 'NON_RESIDENT_OTHER', 'OTHER')),
	CONSTRAINT ck_party_withholding_profile_party_withholding_profile_p_e762 CHECK (pan_status IN ('VERIFIED', 'NOT_AVAILABLE', 'INOPERATIVE')),
	CONSTRAINT ck_party_withholding_profile_party_withholding_profile_pan CHECK ((pan_status <> 'VERIFIED' OR pan_identifier_id IS NOT NULL) AND (pan_status <> 'NOT_AVAILABLE' OR pan_identifier_id IS NULL)),
	CONSTRAINT ck_party_withholding_profile_party_withholding_profile_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	INDEX ix_party_withholding_profile_asof (tenant_id, company_id, valid_from, id),
	INDEX ix_party_withholding_profile_page (tenant_id, company_id, id),
	INDEX ix_party_withholding_profile_ref1 (tenant_id, company_id, pan_identifier_id),
	INDEX ix_party_withholding_profile_ref2 (tenant_id, company_id, default_section_id),
	INDEX ix_party_withholding_profile_tenant_id (tenant_id),
	INDEX ix_party_withholding_profile_term (tenant_id, company_id, party_id, kind, valid_from)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE party_withholding_profile"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
