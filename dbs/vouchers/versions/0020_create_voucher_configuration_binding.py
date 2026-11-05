"""Create voucher_configuration_binding; one DDL statement in each direction."""
from alembic import op

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_configuration_binding (\n\tconfiguration_revision_id BINARY(16) NOT NULL, \n\ttype_id BINARY(16), \n\tfamily VARCHAR(20) NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_configuration_binding PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_configuration_binding_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_configuration_binding_1 FOREIGN KEY(tenant_id, company_id, configuration_revision_id) REFERENCES voucher_configuration_revision (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_configuration_binding_2 FOREIGN KEY(tenant_id, company_id, type_id) REFERENCES voucher_type (tenant_id, company_id, id), \n\tCONSTRAINT ck_voucher_configuration_binding_binding_dates CHECK (valid_to IS NULL OR valid_to > valid_from),\n\tKEY ix_voucher_configuration_binding_0 (tenant_id, company_id, type_id, family, valid_from),\n\tKEY ix_voucher_configuration_binding_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_configuration_binding")
