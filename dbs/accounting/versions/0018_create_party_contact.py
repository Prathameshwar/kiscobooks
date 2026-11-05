"""Create party_contact; exactly one DDL statement in each direction."""
from alembic import op

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_contact (\n\tparty_id BINARY(16) NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tdesignation VARCHAR(100), \n\tdepartment VARCHAR(100), \n\temail VARCHAR(254), \n\tphone VARCHAR(40), \n\tmobile VARCHAR(40), \n\tlanguage VARCHAR(20), \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_contact PRIMARY KEY (id), \n\tCONSTRAINT fk_party_contact_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT uq_party_contact_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_contact_party_contact_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT ck_party_contact_party_contact_version CHECK (row_version > 0),\n\tKEY ix_party_contact_name (tenant_id, company_id, name, id),\n\tKEY ix_party_contact_page (tenant_id, company_id, id),\n\tKEY ix_party_contact_ref0 (tenant_id, company_id, party_id),\n\tKEY ix_party_contact_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_contact")
