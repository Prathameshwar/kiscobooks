"""voucher_charge_dependency; one atomic CREATE with revision-scoped ownership."""
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

UPGRADE = 'CREATE TABLE voucher_charge_dependency (\n\trevision_id BINARY(16) NOT NULL, \n\tcharge_id BINARY(16) NOT NULL, \n\tdepends_on_id BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_charge_dependency PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_charge_dependency_revision FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id), \n\tCONSTRAINT ck_voucher_charge_dependency_voucher_charge_dependency_distinct CHECK (charge_id <> depends_on_id), \n\tCONSTRAINT fk_voucher_charge_dependency_charge_id FOREIGN KEY(tenant_id, company_id, revision_id, charge_id) REFERENCES voucher_charge_detail (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT uq_voucher_charge_dependency_tenant_id_company_id_revision_id_id UNIQUE (tenant_id, company_id, revision_id, id), \n\tCONSTRAINT uq_voucher_charge_dependency_tenant_id_company_id_revisi_1e29 UNIQUE (tenant_id, company_id, revision_id, charge_id, depends_on_id), \n\tCONSTRAINT uq_voucher_charge_dependency_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_charge_dependency_depends_on_id FOREIGN KEY(tenant_id, company_id, revision_id, depends_on_id) REFERENCES voucher_charge_detail (tenant_id, company_id, revision_id, id),\n\tINDEX ix_voucher_charge_dependency_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(UPGRADE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_charge_dependency")
