"""Create voucher_custom_index; one DDL statement in each direction."""
from alembic import op

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_custom_index (\n\tentity_type VARCHAR(40) NOT NULL, \n\tentity_id BINARY(16) NOT NULL, \n\tvoucher_id BINARY(16) NOT NULL, \n\trevision_id BINARY(16) NOT NULL, \n\tfield_key VARCHAR(64) NOT NULL, \n\tmember_number INTEGER NOT NULL, \n\tvalue_text VARCHAR(200) COLLATE utf8mb4_bin, \n\tvalue_number NUMERIC(19, 4), \n\tvalue_date DATE, \n\tvalue_datetime_at DATETIME(6), \n\tvalue_bool BOOL, \n\tcurrency VARCHAR(3), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_custom_index PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_custom_index_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_custom_index_tenant_id_company_id_entity_id_f_7ceb UNIQUE (tenant_id, company_id, entity_id, field_key, member_number), \n\tCONSTRAINT fk_voucher_custom_index_1 FOREIGN KEY(tenant_id, company_id, voucher_id) REFERENCES voucher (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_custom_index_2 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id),\n\tKEY ix_voucher_custom_index_0 (tenant_id, company_id, entity_type, field_key, value_text, voucher_id),\n\tKEY ix_voucher_custom_index_1 (tenant_id, company_id, entity_type, field_key, value_number, voucher_id),\n\tKEY ix_voucher_custom_index_2 (tenant_id, company_id, entity_type, field_key, value_date, voucher_id),\n\tKEY ix_voucher_custom_index_3 (tenant_id, company_id, entity_type, field_key, value_datetime_at, voucher_id),\n\tKEY ix_voucher_custom_index_4 (tenant_id, company_id, entity_type, field_key, value_bool, voucher_id),\n\tKEY ix_voucher_custom_index_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_custom_index")
