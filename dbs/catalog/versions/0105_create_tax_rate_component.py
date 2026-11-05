"""Create tax_rate_component; one reversible DDL."""
from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE tax_rate_component (
	rate_id BINARY(16) NOT NULL,
	component_key VARCHAR(30) NOT NULL,
	component VARCHAR(5) NOT NULL,
	kind VARCHAR(14) NOT NULL,
	percentage NUMERIC(19,4) NULL,
	amount NUMERIC(19,4) NULL,
	currency VARCHAR(3) NULL,
	unit_id BINARY(16) NULL,
	basis_quantity NUMERIC(19,4) NULL,
	rounding_mode VARCHAR(7) NOT NULL,
	position INTEGER NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_tax_rate_component PRIMARY KEY (id),
	CONSTRAINT uq_tax_rate_component_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rate_component_version CHECK (row_version >= 1),
	CONSTRAINT fk_tax_component_rate_id FOREIGN KEY(tenant_id, company_id, rate_id) REFERENCES tax_rate (tenant_id, company_id, id),
	CONSTRAINT fk_tax_component_unit_id FOREIGN KEY(tenant_id, company_id, unit_id) REFERENCES unit_of_measure (tenant_id, company_id, id),
	CONSTRAINT uq_tax_component_key UNIQUE (tenant_id, company_id, rate_id, component_key),
	CONSTRAINT ck_tax_rate_component_component CHECK (component IN ('CGST','SGST','UTGST','IGST','CESS')),
	CONSTRAINT ck_tax_rate_component_shape CHECK ((kind = 'PERCENT' AND percentage IS NOT NULL AND percentage >= 0 AND (component = 'CESS' OR percentage <= 100) AND amount IS NULL AND currency IS NULL AND unit_id IS NULL AND basis_quantity IS NULL) OR (kind = 'FIXED_PER_UNIT' AND component = 'CESS' AND percentage IS NULL AND amount IS NOT NULL AND amount > 0 AND currency IS NOT NULL AND unit_id IS NOT NULL AND basis_quantity IS NOT NULL AND basis_quantity > 0)),
	CONSTRAINT ck_tax_rate_component_rounding CHECK (rounding_mode IN ('HALF_UP','UP','DOWN')),
	CONSTRAINT ck_tax_rate_component_position CHECK (position BETWEEN 0 AND 15),
    INDEX ix_tax_component_order (tenant_id, company_id, rate_id, position, id),
    INDEX ix_tax_rate_component_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE tax_rate_component")
