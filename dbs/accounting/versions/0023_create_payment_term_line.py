"""Create payment_term_line; exactly one DDL statement in each direction."""
from alembic import op

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE payment_term_line (\n\tpayment_term_id BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tpercentage NUMERIC(7, 4) NOT NULL, \n\tbasis VARCHAR(40) NOT NULL, \n\tdays INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_payment_term_line PRIMARY KEY (id), \n\tCONSTRAINT ck_payment_term_line_payment_term_line_version CHECK (row_version > 0), \n\tCONSTRAINT ck_payment_term_line_payment_term_line_basis CHECK (basis IN ('INVOICE_DATE', 'MONTH_END')), \n\tCONSTRAINT uq_payment_term_line_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_payment_term_line_payment_term_id FOREIGN KEY(tenant_id, company_id, payment_term_id) REFERENCES payment_term (tenant_id, company_id, id), \n\tCONSTRAINT uq_payment_term_line_0 UNIQUE (tenant_id, company_id, payment_term_id, sequence),\n\tKEY ix_payment_term_line_page (tenant_id, company_id, id),\n\tKEY ix_payment_term_line_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE payment_term_line")
