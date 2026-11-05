"""Create party_credit_policy; exactly one DDL statement in each direction."""
from alembic import op

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None

CREATE = "CREATE TABLE party_credit_policy (\n\tparty_id BINARY(16) NOT NULL, \n\t`role` VARCHAR(40) NOT NULL, \n\tlimit_mode VARCHAR(40) NOT NULL, \n\tlimit_amount NUMERIC(19, 4), \n\tcurrency VARCHAR(3) NOT NULL, \n\tenforcement VARCHAR(40) NOT NULL, \n\toverdue_days INTEGER NOT NULL, \n\toverdue_tolerance NUMERIC(19, 4) NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_party_credit_policy PRIMARY KEY (id), \n\tCONSTRAINT uq_party_credit_policy_0 UNIQUE (tenant_id, company_id, party_id, `role`, valid_from), \n\tCONSTRAINT fk_party_credit_policy_party_id FOREIGN KEY(tenant_id, company_id, party_id) REFERENCES party (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_credit_policy_party_credit_policy_dates CHECK (valid_to IS NULL OR valid_to >= valid_from), \n\tCONSTRAINT ck_party_credit_policy_party_credit_policy_role CHECK (role IN ('CUSTOMER', 'SUPPLIER')), \n\tCONSTRAINT ck_party_credit_policy_party_credit_policy_version CHECK (row_version > 0), \n\tCONSTRAINT ck_party_credit_policy_party_credit_policy_limit_mode CHECK (limit_mode IN ('INHERIT', 'UNLIMITED', 'LIMITED')), \n\tCONSTRAINT uq_party_credit_policy_scope UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT ck_party_credit_policy_party_credit_policy_enforcement CHECK (enforcement IN ('WARN', 'BLOCK', 'OVERRIDE')),\n\tKEY ix_party_credit_policy_page (tenant_id, company_id, id),\n\tKEY ix_party_credit_policy_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE party_credit_policy")
