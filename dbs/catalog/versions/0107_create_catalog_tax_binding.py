"""Create catalog_tax_binding; one reversible DDL."""
from alembic import op

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE catalog_tax_binding (
	scope_id BINARY(16) NOT NULL,
	jurisdiction VARCHAR(2) NOT NULL,
	direction VARCHAR(8) NOT NULL,
	bundle VARCHAR(14) NOT NULL,
	mode VARCHAR(16) NOT NULL,
	classification_id BINARY(16) NULL,
	treatment VARCHAR(10) NULL,
	exemption_reason VARCHAR(500) NULL,
	tax_category_id BINARY(16) NULL,
	rule_id BINARY(16) NULL,
	valid_from DATE NOT NULL,
	valid_to DATE NULL,
	source_reference VARCHAR(500) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_catalog_tax_binding PRIMARY KEY (id),
	CONSTRAINT uq_catalog_tax_binding_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_catalog_tax_binding_version CHECK (row_version >= 1),
	CONSTRAINT ck_catalog_tax_binding_start CHECK (valid_from >= '1000-01-01'),
	CONSTRAINT ck_catalog_tax_binding_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
	CONSTRAINT uq_catalog_tax_binding_start UNIQUE (tenant_id, company_id, scope_id, direction, bundle, valid_from),
	CONSTRAINT fk_tax_binding_scope_id FOREIGN KEY(tenant_id, company_id, scope_id) REFERENCES catalog_tax_scope (tenant_id, company_id, id),
	CONSTRAINT fk_tax_binding_classification_id FOREIGN KEY(tenant_id, company_id, classification_id) REFERENCES tax_classification (tenant_id, company_id, id),
	CONSTRAINT fk_tax_binding_tax_category_id FOREIGN KEY(tenant_id, company_id, tax_category_id) REFERENCES tax_category (tenant_id, company_id, id),
	CONSTRAINT fk_tax_binding_rule_id FOREIGN KEY(tenant_id, company_id, rule_id) REFERENCES tax_rule (tenant_id, company_id, id),
	CONSTRAINT ck_catalog_tax_binding_jurisdiction CHECK (jurisdiction = 'IN'),
	CONSTRAINT ck_catalog_tax_binding_direction CHECK (direction IN ('SALE','PURCHASE')),
	CONSTRAINT ck_catalog_tax_binding_bundle CHECK (bundle IN ('CLASSIFICATION','TREATMENT','RULE')),
	CONSTRAINT ck_catalog_tax_binding_treatment CHECK (treatment IS NULL OR treatment IN ('TAXABLE','NIL_RATED','EXEMPT','NON_GST')),
	CONSTRAINT ck_catalog_tax_binding_shape CHECK ((mode IN ('INHERIT','REQUIRE_EXPLICIT') AND classification_id IS NULL AND treatment IS NULL AND exemption_reason IS NULL AND tax_category_id IS NULL AND rule_id IS NULL) OR (mode = 'OVERRIDE' AND ((bundle = 'CLASSIFICATION' AND classification_id IS NOT NULL AND treatment IS NULL AND exemption_reason IS NULL AND tax_category_id IS NULL AND rule_id IS NULL) OR (bundle = 'TREATMENT' AND classification_id IS NULL AND rule_id IS NULL AND treatment IS NOT NULL AND tax_category_id IS NOT NULL AND ((treatment IN ('EXEMPT','NON_GST') AND exemption_reason IS NOT NULL) OR (treatment IN ('TAXABLE','NIL_RATED') AND exemption_reason IS NULL))) OR (bundle = 'RULE' AND rule_id IS NOT NULL AND classification_id IS NULL AND treatment IS NULL AND exemption_reason IS NULL AND tax_category_id IS NULL)))),
    INDEX ix_catalog_tax_binding_date (tenant_id, company_id, scope_id, direction, bundle, valid_from, id),
    INDEX ix_catalog_tax_binding_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE catalog_tax_binding")
