"""Create party_accounting_policy; exactly one DDL statement in each direction."""
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_accounting_policy (\n\tparty_id BINARY(16) NOT NULL, \n\t`role` VARCHAR(40) NOT NULL, \n\tpayment_term_id BINARY(16) NOT NULL, \n\tbill_wise BOOL NOT NULL, \n\tsettlement_currency VARCHAR(3) NOT NULL, \n\ttransaction_hold BOOL NOT NULL, \n\tpayment_hold BOOL NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_accounting_policy PRIMARY KEY (id), \n\tCONSTRAINT ck_party_accounting_policy_party_accounting_policy_dates CHECK (valid_to IS NULL OR valid_to >= valid_from), \n\tCONSTRAINT ck_party_accounting_policy_party_accounting_policy_role CHECK (role IN ('CUSTOMER', 'SUPPLIER')), \n\tCONSTRAINT uq_party_accounting_policy_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_party_accounting_policy_payment_term_id FOREIGN KEY(tenant_id, company_id, payment_term_id) REFERENCES payment_term (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_accounting_policy_party_accounting_policy_version CHECK (row_version > 0), \n\tCONSTRAINT uq_party_accounting_policy_0 UNIQUE (tenant_id, company_id, party_id, `role`, valid_from), \n\tCONSTRAINT fk_party_accounting_policy_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id),\n\tKEY ix_party_accounting_policy_page (tenant_id, company_id, id),\n\tKEY ix_party_accounting_policy_ref1 (tenant_id, company_id, payment_term_id),\n\tKEY ix_party_accounting_policy_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_accounting_policy")
