"""Create voucher_master_evidence; one DDL statement in each direction."""
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_master_evidence (\n\towner VARCHAR(30) NOT NULL, \n\tentity_type VARCHAR(40) NOT NULL, \n\tsource_id BINARY(16) NOT NULL, \n\tsource_version BIGINT NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tfacts JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_master_evidence PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_master_evidence_tenant_id_company_id_owner_en_906b UNIQUE (tenant_id, company_id, owner, entity_type, source_id), \n\tCONSTRAINT uq_voucher_master_evidence_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_master_evidence_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_master_evidence")
