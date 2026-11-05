"""Create account_template_binding; exactly one DDL statement in each direction."""
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE account_template_binding (\n\tinstallation_id BINARY(16) NOT NULL, \n\tobject_type VARCHAR(40) NOT NULL, \n\tobject_id BINARY(16) NOT NULL, \n\tsystem_key VARCHAR(60) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_account_template_binding PRIMARY KEY (id), \n\tCONSTRAINT fk_account_template_binding_installation_id FOREIGN KEY(tenant_id, company_id, installation_id) REFERENCES account_template_installation (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_template_binding_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT uq_account_template_binding_0 UNIQUE (tenant_id, company_id, installation_id, system_key), \n\tCONSTRAINT ck_account_template_binding_account_template_binding_object_type CHECK (object_type IN ('HEAD', 'GROUP', 'ACCOUNT')), \n\tCONSTRAINT ck_account_template_binding_account_template_binding_version CHECK (row_version > 0),\n\tKEY ix_account_template_binding_page (tenant_id, company_id, id),\n\tKEY ix_account_template_binding_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE account_template_binding")
