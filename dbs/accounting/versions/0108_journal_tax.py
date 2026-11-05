"""journal_tax; one atomic CREATE including supporting indexes.

Tax Analysis evidence for a tax-bearing voucher (tax-accounting Phase 8). Downgrade drops
the table; it holds no row another table references.
"""
from alembic import op

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE journal_tax (
	journal_id BINARY(16) NOT NULL,
	direction VARCHAR(8) NOT NULL,
	party_id BINARY(16),
	company_registration_id BINARY(16),
	party_registration_id BINARY(16),
	place_of_supply VARCHAR(10),
	supply_context VARCHAR(12),
	supply_reason VARCHAR(16),
	reverse_charge BOOL NOT NULL,
	currency VARCHAR(3) NOT NULL,
	taxable_value NUMERIC(19, 4) NOT NULL,
	tax_total NUMERIC(19, 4) NOT NULL,
	withholding_kind VARCHAR(3),
	withholding_section_id BINARY(16),
	withholding_amount NUMERIC(19, 4),
	withholding_base NUMERIC(19, 4),
	withholding_tax NUMERIC(19, 4),
	certificate_id BINARY(16),
	certificate_base NUMERIC(19, 4),
	line_count INTEGER NOT NULL,
	request JSON NOT NULL,
	snapshot JSON NOT NULL,
	snapshot_hash VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_journal_tax PRIMARY KEY (id),
	CONSTRAINT uq_journal_tax_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_journal_tax_journal UNIQUE (tenant_id, company_id, journal_id),
	CONSTRAINT ck_journal_tax_journal_tax_version CHECK (row_version > 0),
	CONSTRAINT fk_journal_tax_journal_id FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id),
	CONSTRAINT fk_journal_tax_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),
	CONSTRAINT fk_journal_tax_party_registration_id FOREIGN KEY(tenant_id, company_id, party_registration_id) REFERENCES party_tax_registration (tenant_id, company_id, id),
	CONSTRAINT fk_journal_tax_withholding_section_id FOREIGN KEY(tenant_id, company_id, withholding_section_id) REFERENCES withholding_section (tenant_id, company_id, id),
	CONSTRAINT fk_journal_tax_certificate_id FOREIGN KEY(tenant_id, company_id, certificate_id) REFERENCES withholding_certificate (tenant_id, company_id, id),
	CONSTRAINT ck_journal_tax_journal_tax_direction CHECK (direction IN ('SALE', 'PURCHASE')),
	CONSTRAINT ck_journal_tax_journal_tax_amount CHECK (taxable_value >= 0 AND tax_total >= 0 AND line_count BETWEEN 1 AND 200),
	CONSTRAINT ck_journal_tax_journal_tax_withholding CHECK ((withholding_kind IS NULL AND withholding_section_id IS NULL AND withholding_amount IS NULL AND withholding_base IS NULL AND withholding_tax IS NULL AND certificate_id IS NULL AND certificate_base IS NULL) OR (withholding_kind IN ('TDS', 'TCS') AND withholding_section_id IS NOT NULL AND withholding_amount >= 0 AND withholding_base >= 0 AND withholding_tax >= 0 AND ((certificate_id IS NULL AND certificate_base IS NULL) OR (certificate_id IS NOT NULL AND certificate_base >= 0)))),
	CONSTRAINT ck_journal_tax_journal_tax_hash CHECK (LENGTH(snapshot_hash) = 64),
	INDEX ix_journal_tax_certificate (tenant_id, company_id, certificate_id),
	INDEX ix_journal_tax_page (tenant_id, company_id, id),
	INDEX ix_journal_tax_registration (tenant_id, company_id, party_registration_id),
	INDEX ix_journal_tax_section (tenant_id, company_id, withholding_section_id),
	INDEX ix_journal_tax_tenant_id (tenant_id),
	INDEX ix_journal_tax_withholding (tenant_id, company_id, party_id, withholding_section_id, id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE journal_tax"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
