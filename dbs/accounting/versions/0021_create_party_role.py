"""Create party_role; exactly one DDL statement in each direction."""
from alembic import op

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_role (\n\tparty_id BINARY(16) NOT NULL, \n\t`role` VARCHAR(40) NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_role PRIMARY KEY (id), \n\tCONSTRAINT uq_party_role_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_role_party_role_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT fk_party_role_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_role_party_role_version CHECK (row_version > 0), \n\tCONSTRAINT uq_party_role_0 UNIQUE (tenant_id, company_id, party_id, `role`), \n\tCONSTRAINT ck_party_role_party_role_role CHECK (role IN ('CUSTOMER', 'SUPPLIER', 'OTHER')),\n\tKEY ix_party_role_page (tenant_id, company_id, id),\n\tKEY ix_party_role_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_role")
