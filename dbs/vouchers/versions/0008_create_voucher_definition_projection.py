"""voucher_definition_projection; one atomic CREATE including scoped indexes."""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_definition_projection (\n\tentity_type VARCHAR(40) NOT NULL, \n\tfield_key VARCHAR(64) NOT NULL, \n\tsource_version BIGINT NOT NULL, \n\tdefinition JSON NOT NULL, \n\tpresentation JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tused_at DATETIME(6), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_definition_projection PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_definition_projection_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_definition_projection_tenant_id_company_id_en_e18e UNIQUE (tenant_id, company_id, entity_type, field_key),\n\tINDEX ix_voucher_definition_projection_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_definition_projection")
