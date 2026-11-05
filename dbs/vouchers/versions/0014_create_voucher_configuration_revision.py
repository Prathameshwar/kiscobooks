"""Create voucher_configuration_revision; one DDL statement in each direction."""
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_configuration_revision (\n\tprofile_id BINARY(16) NOT NULL, \n\trevision_number INTEGER NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tpolicy JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_configuration_revision PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_configuration_revision_tenant_id_company_id_p_0cb1 UNIQUE (tenant_id, company_id, profile_id, revision_number), \n\tCONSTRAINT fk_voucher_configuration_revision_1 FOREIGN KEY(tenant_id, company_id, profile_id) REFERENCES voucher_configuration_profile (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_configuration_revision_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_configuration_revision_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_configuration_revision")
