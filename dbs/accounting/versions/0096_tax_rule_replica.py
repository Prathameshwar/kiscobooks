"""tax_rule_replica: Catalog GST rule replica; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE tax_rule_replica (
	code VARCHAR(30) NOT NULL,
	name VARCHAR(100) NOT NULL,
	tax_system VARCHAR(10) NOT NULL,
	jurisdiction VARCHAR(2) NOT NULL,
	item_kind VARCHAR(7) NOT NULL,
	treatment VARCHAR(10) NOT NULL,
	tax_category_id BINARY(16) NOT NULL,
	is_active BOOL NOT NULL,
	source_reference VARCHAR(500) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	source_version BIGINT NOT NULL,
	source_message_id BINARY(16) NOT NULL,
	replicated_at DATETIME(6) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	CONSTRAINT pk_tax_rule_replica PRIMARY KEY (id),
	CONSTRAINT ck_tax_rule_replica_shape CHECK (tax_system = 'gst_in' AND jurisdiction = 'IN' AND item_kind IN ('GOODS','SERVICE') AND treatment IN ('TAXABLE','NIL_RATED','EXEMPT','NON_GST')),
	CONSTRAINT ck_tax_rule_replica_source_version CHECK (source_version >= 1),
	CONSTRAINT uq_tax_rule_replica_code UNIQUE (tenant_id, company_id, code),
	CONSTRAINT uq_tax_rule_replica_scope UNIQUE (tenant_id, company_id, id),
	INDEX ix_tax_rule_replica_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE tax_rule_replica"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
