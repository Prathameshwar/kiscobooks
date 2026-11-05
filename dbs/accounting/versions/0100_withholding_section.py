"""withholding_section; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE withholding_section (
	code VARCHAR(40) NOT NULL,
	kind VARCHAR(10) NOT NULL,
	name VARCHAR(160) NOT NULL,
	description VARCHAR(500),
	status VARCHAR(40) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16),
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16),
	CONSTRAINT pk_withholding_section PRIMARY KEY (id),
	CONSTRAINT uq_withholding_section_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_withholding_section_withholding_section_version CHECK (row_version > 0),
	CONSTRAINT uq_withholding_section_0 UNIQUE (tenant_id, company_id, kind, code),
	CONSTRAINT ck_withholding_section_withholding_section_kind CHECK (kind IN ('TDS', 'TCS')),
	CONSTRAINT ck_withholding_section_withholding_section_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')),
	INDEX ix_withholding_section_name (tenant_id, company_id, name, id),
	INDEX ix_withholding_section_page (tenant_id, company_id, id),
	INDEX ix_withholding_section_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE withholding_section"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
