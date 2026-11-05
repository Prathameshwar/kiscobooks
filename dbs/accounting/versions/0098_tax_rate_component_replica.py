"""tax_rate_component_replica: Catalog GST rate component replica; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE tax_rate_component_replica (
	rate_id BINARY(16) NOT NULL,
	component_key VARCHAR(30) NOT NULL,
	component VARCHAR(5) NOT NULL,
	kind VARCHAR(14) NOT NULL,
	percentage NUMERIC(19, 4),
	amount NUMERIC(19, 4),
	currency VARCHAR(3),
	unit_id BINARY(16),
	basis_quantity NUMERIC(19, 4),
	rounding_mode VARCHAR(7) NOT NULL,
	position INTEGER NOT NULL,
	company_id BINARY(16) NOT NULL,
	source_version BIGINT NOT NULL,
	source_message_id BINARY(16) NOT NULL,
	replicated_at DATETIME(6) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	CONSTRAINT pk_tax_rate_component_replica PRIMARY KEY (id),
	CONSTRAINT uq_tax_rate_component_replica_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_rate_component_replica_component CHECK (component IN ('CGST','SGST','UTGST','IGST','CESS') AND rounding_mode IN ('HALF_UP','UP','DOWN') AND position BETWEEN 0 AND 15),
	CONSTRAINT ck_tax_rate_component_replica_source_version CHECK (source_version >= 1),
	CONSTRAINT uq_tax_rate_component_key UNIQUE (tenant_id, company_id, rate_id, component_key),
	CONSTRAINT ck_tax_rate_component_replica_shape CHECK ((kind = 'PERCENT' AND percentage IS NOT NULL AND percentage >= 0 AND (component = 'CESS' OR percentage <= 100) AND amount IS NULL AND currency IS NULL AND unit_id IS NULL AND basis_quantity IS NULL) OR (kind = 'FIXED_PER_UNIT' AND component = 'CESS' AND percentage IS NULL AND amount IS NOT NULL AND amount > 0 AND currency IS NOT NULL AND unit_id IS NOT NULL AND basis_quantity IS NOT NULL AND basis_quantity > 0)),
	CONSTRAINT fk_tax_rate_component_replica_rate_id FOREIGN KEY(tenant_id, company_id, rate_id) REFERENCES tax_rate_replica (tenant_id, company_id, id),
	INDEX ix_tax_rate_component_replica_order (tenant_id, company_id, rate_id, position, id),
	INDEX ix_tax_rate_component_replica_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE tax_rate_component_replica"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
