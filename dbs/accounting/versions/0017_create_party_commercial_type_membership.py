"""Create party_commercial_type_membership; exactly one DDL statement in each direction."""
from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE party_commercial_type_membership (\n\tparty_id BINARY(16) NOT NULL, \n\tcommercial_type_id BINARY(16) NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_commercial_type_membership PRIMARY KEY (id), \n\tCONSTRAINT ck_party_commercial_type_membership_party_commercial_typ_c7fb CHECK (valid_to IS NULL OR valid_to >= valid_from), \n\tCONSTRAINT ck_party_commercial_type_membership_party_commercial_typ_247f CHECK (row_version > 0), \n\tCONSTRAINT uq_party_commercial_type_membership_0 UNIQUE (tenant_id, company_id, party_id, commercial_type_id, valid_from), \n\tCONSTRAINT fk_party_commercial_type_membership_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT uq_party_commercial_type_membership_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_party_commercial_type_membership_commercial_type_id FOREIGN KEY(tenant_id, company_id, commercial_type_id) REFERENCES party_commercial_type (tenant_id, company_id, id),\n\tKEY ix_party_commercial_type_membership_page (tenant_id, company_id, id),\n\tKEY ix_party_commercial_type_membership_ref0 (tenant_id, company_id, commercial_type_id),\n\tKEY ix_party_commercial_type_membership_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_commercial_type_membership")
