"""Create party_commercial_type; exactly one DDL statement in each direction."""
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_commercial_type (\n\tcode VARCHAR(40) NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\t`role` VARCHAR(40) NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_commercial_type PRIMARY KEY (id), \n\tCONSTRAINT ck_party_commercial_type_party_commercial_type_version CHECK (row_version > 0), \n\tCONSTRAINT uq_party_commercial_type_0 UNIQUE (tenant_id, company_id, code), \n\tCONSTRAINT ck_party_commercial_type_party_commercial_type_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT ck_party_commercial_type_party_commercial_type_role CHECK (role IN ('CUSTOMER', 'SUPPLIER')), \n\tCONSTRAINT uq_party_commercial_type_scope UNIQUE (tenant_id, company_id, id),\n\tKEY ix_party_commercial_type_name (tenant_id, company_id, name, id),\n\tKEY ix_party_commercial_type_page (tenant_id, company_id, id),\n\tKEY ix_party_commercial_type_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_commercial_type")
