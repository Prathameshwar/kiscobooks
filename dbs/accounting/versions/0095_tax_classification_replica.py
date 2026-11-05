"""tax_classification_replica: Catalog GST classification replica; one atomic CREATE including supporting indexes."""
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE tax_classification_replica (
	jurisdiction VARCHAR(2) NOT NULL,
	code_system VARCHAR(3) NOT NULL,
	code VARCHAR(8) NOT NULL,
	item_kind VARCHAR(7) NOT NULL,
	description VARCHAR(1000) NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE,
	source_reference VARCHAR(500) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	company_id BINARY(16) NOT NULL,
	source_version BIGINT NOT NULL,
	source_message_id BINARY(16) NOT NULL,
	replicated_at DATETIME(6) NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	CONSTRAINT pk_tax_classification_replica PRIMARY KEY (id),
	CONSTRAINT ck_tax_classification_replica_kind CHECK (jurisdiction = 'IN' AND ((code_system = 'HSN' AND item_kind = 'GOODS') OR (code_system = 'SAC' AND item_kind = 'SERVICE'))),
	CONSTRAINT uq_tax_classification_replica_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_tax_classification_replica_source_version CHECK (source_version >= 1),
	CONSTRAINT ck_tax_classification_replica_dates CHECK (valid_from >= '1000-01-01' AND (valid_to IS NULL OR valid_to >= valid_from)),
	INDEX ix_tax_classification_replica_code (tenant_id, company_id, code_system, code, valid_from, id),
	INDEX ix_tax_classification_replica_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""
DOWNGRADE = "DROP TABLE tax_classification_replica"

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute(DOWNGRADE)
