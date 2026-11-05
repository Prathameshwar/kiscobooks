"""Create voucher_artifact; one DDL statement in each direction."""
from alembic import op

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_artifact (\n\trevision_id BINARY(16) NOT NULL, \n\ttemplate_revision_id BINARY(16) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tcontent_hash VARCHAR(64), \n\tbody MEDIUMTEXT, \n\tpermission_hash VARCHAR(64) NOT NULL, \n\trender_context_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_artifact PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_artifact_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_artifact_tenant_id_company_id_revision_id_tem_fbb3 UNIQUE (tenant_id, company_id, revision_id, template_revision_id, permission_hash, render_context_hash), \n\tCONSTRAINT fk_voucher_artifact_1 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_artifact_2 FOREIGN KEY(tenant_id, company_id, template_revision_id) REFERENCES voucher_template_revision (tenant_id, company_id, id),\n\tKEY ix_voucher_artifact_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_artifact")
