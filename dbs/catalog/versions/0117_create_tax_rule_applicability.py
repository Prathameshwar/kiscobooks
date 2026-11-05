"""Create tax_rule_applicability; one reversible DDL."""
from alembic import op

revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_rule_applicability (
	rule_id BINARY(16) NOT NULL,
	code_system VARCHAR(3) NOT NULL,
	code VARCHAR(8) NOT NULL,
	match_kind VARCHAR(6) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_rule_applicability PRIMARY KEY (id),
	CONSTRAINT uq_tax_rule_applicability_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rule_applicability_version CHECK (row_version >= 1),
	CONSTRAINT fk_tax_applicability_rule_id FOREIGN KEY(tenant_id, company_id, rule_id) REFERENCES tax_rule (tenant_id, company_id, id),
	CONSTRAINT uq_tax_applicability_match UNIQUE (tenant_id, company_id, rule_id, code_system, code, match_kind),
	CONSTRAINT ck_tax_rule_applicability_match CHECK (code_system IN ('HSN','SAC') AND match_kind IN ('EXACT','PREFIX')),
    INDEX ix_tax_rule_applicability_tenant_id (tenant_id)
)CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE tax_rule_applicability")
