"""voucher_field_adoption; one atomic CREATE including scoped indexes."""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_field_adoption (\n\tdefinition_id BINARY(16) NOT NULL, \n\tsource_version BIGINT NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tdefinition JSON NOT NULL, \n\tpresentation JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_field_adoption PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_field_adoption_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_field_adoption_tenant_id_company_id_definitio_2538 UNIQUE (tenant_id, company_id, definition_id, source_version), \n\tCONSTRAINT fk_voucher_field_adoption_1 FOREIGN KEY(tenant_id, company_id, definition_id) REFERENCES voucher_definition_projection (tenant_id, company_id, id),\n\tINDEX ix_voucher_field_adoption_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_field_adoption")
