"""Derived lineage; one atomic CREATE with scope and lookup constraints."""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE report_journal_link (
	version_id BINARY(16) NOT NULL,
	epoch_id BINARY(16) NOT NULL,
	journal_id BINARY(16) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_report_journal_link PRIMARY KEY (id),
	CONSTRAINT uq_report_journal_link_effect UNIQUE (tenant_id, company_id, version_id, journal_id),
	CONSTRAINT uq_report_journal_link_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT fk_report_journal_link_version_id FOREIGN KEY(tenant_id, company_id, version_id) REFERENCES report_fact_version (tenant_id, company_id, id),
	CONSTRAINT fk_report_journal_link_epoch_id FOREIGN KEY(tenant_id, company_id, epoch_id) REFERENCES report_source_epoch (tenant_id, company_id, id),
	INDEX ix_report_journal_link_lookup (tenant_id, company_id, epoch_id, journal_id, version_id),
	INDEX ix_report_journal_link_page (tenant_id, company_id, id),
	INDEX ix_report_journal_link_tenant_id (tenant_id)
)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE report_journal_link")
