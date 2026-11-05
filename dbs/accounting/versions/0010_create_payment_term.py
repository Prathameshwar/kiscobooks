"""Create payment_term; exactly one DDL statement in each direction."""
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE payment_term (\n\tcode VARCHAR(40) NOT NULL, \n\tname VARCHAR(160) NOT NULL, \n\tdescription VARCHAR(500), \n\tstatus VARCHAR(40) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_payment_term PRIMARY KEY (id), \n\tCONSTRAINT uq_payment_term_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_payment_term_payment_term_status CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE')), \n\tCONSTRAINT uq_payment_term_0 UNIQUE (tenant_id, company_id, code), \n\tCONSTRAINT ck_payment_term_payment_term_version CHECK (row_version > 0),\n\tKEY ix_payment_term_name (tenant_id, company_id, name, id),\n\tKEY ix_payment_term_page (tenant_id, company_id, id),\n\tKEY ix_payment_term_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE payment_term")
