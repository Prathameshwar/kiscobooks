"""Create party_contact_use; exactly one DDL statement in each direction."""
from alembic import op

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_contact_use (\n\tparty_id BINARY(16) NOT NULL, \n\tcontact_id BINARY(16) NOT NULL, \n\tpurpose VARCHAR(40) NOT NULL, \n\tis_default BOOL NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_contact_use PRIMARY KEY (id), \n\tCONSTRAINT ck_party_contact_use_party_contact_use_version CHECK (row_version > 0), \n\tCONSTRAINT ck_party_contact_use_party_contact_use_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT fk_party_contact_use_contact_id FOREIGN KEY(tenant_id, company_id, contact_id) REFERENCES party_contact (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_contact_use_party_contact_use_purpose CHECK (purpose IN ('GENERAL', 'INVOICING', 'PAYMENTS', 'DELIVERY')), \n\tCONSTRAINT uq_party_contact_use_0 UNIQUE (tenant_id, company_id, contact_id, purpose), \n\tCONSTRAINT uq_party_contact_use_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_party_contact_use_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),\n\tKEY ix_party_contact_use_page (tenant_id, company_id, id),\n\tKEY ix_party_contact_use_ref1 (tenant_id, company_id, party_id),\n\tKEY ix_party_contact_use_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_contact_use")
