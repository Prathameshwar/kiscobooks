"""Create commercial_guard_rule; one reversible DDL."""
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE commercial_guard_rule (
    item_id BINARY(16) NOT NULL,
    unit_revision_id BINARY(16) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    numeric_revision_id BINARY(16) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    rule_kind VARCHAR(12) NOT NULL,
    amount NUMERIC(19,4) NULL,
    percentage NUMERIC(19,4) NULL,
    price_basis_quantity NUMERIC(19,4) NOT NULL,
    tax_basis VARCHAR(12) NOT NULL,
    estimate_kind VARCHAR(24) NULL,
    severity VARCHAR(20) NOT NULL,
    source_reference VARCHAR(500) NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_commercial_guard_rule PRIMARY KEY (id),
    CONSTRAINT uq_v97_0 UNIQUE (tenant_id, company_id, id),
    CONSTRAINT uq_v97_1 UNIQUE (tenant_id, company_id, item_id, unit_revision_id, currency, rule_kind, valid_from),
    CONSTRAINT fk_v97_0 FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
    CONSTRAINT fk_v97_1 FOREIGN KEY(tenant_id, company_id, unit_revision_id) REFERENCES item_unit_revision (tenant_id, company_id, id),
    CONSTRAINT fk_v97_2 FOREIGN KEY(tenant_id, company_id, item_id, unit_revision_id, currency, numeric_revision_id) REFERENCES item_price_numeric_revision (tenant_id, company_id, item_id, unit_revision_id, currency, id),
    CONSTRAINT ck_commercial_guard_rule_v97_0 CHECK (row_version >= 1),
    CONSTRAINT ck_commercial_guard_rule_v97_1 CHECK (valid_from >= '1000-01-01'),
    CONSTRAINT ck_commercial_guard_rule_v97_2 CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_commercial_guard_rule_v97_3 CHECK (price_basis_quantity > 0),
    CONSTRAINT ck_commercial_guard_rule_v97_4 CHECK (tax_basis = 'EXCLUSIVE'),
    CONSTRAINT ck_commercial_guard_rule_v97_5 CHECK (severity IN ('BLOCK','REQUIRE_APPROVAL')),
    CONSTRAINT ck_commercial_guard_rule_v97_6 CHECK ((rule_kind IN ('FIXED_MIN','FIXED_MAX') AND amount IS NOT NULL AND amount > 0 AND percentage IS NULL AND estimate_kind IS NULL) OR (rule_kind IN ('MIN_MARGIN','MIN_MARKUP') AND amount IS NULL AND percentage IS NOT NULL AND percentage >= 0 AND estimate_kind IS NOT NULL)),
    CONSTRAINT ck_commercial_guard_rule_v97_7 CHECK (rule_kind <> 'MIN_MARGIN' OR percentage < 100),
    INDEX ix_commercial_guard_rule_tenant_id (tenant_id),
    INDEX ix_v97_0 (tenant_id, company_id, item_id, unit_revision_id, currency, valid_from, id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE commercial_guard_rule")
