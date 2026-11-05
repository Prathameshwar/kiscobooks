"""Create voucher_revision; one DDL statement in each direction."""
from alembic import op

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_revision (\n\tvoucher_id BINARY(16) NOT NULL, \n\trevision_number INTEGER NOT NULL, \n\ttype_revision_id BINARY(16) NOT NULL, \n\tclass_id BINARY(16), \n\tdocument_date DATE NOT NULL, \n\tposting_date DATE, \n\tstock_date DATE, \n\tstatutory_date DATE, \n\tcredit_terms_date DATE, \n\tfiscal_start_date DATE NOT NULL, \n\tmode VARCHAR(20) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tnarration TEXT NOT NULL, \n\tcustom_fields JSON NOT NULL, \n\tdefinition_snapshot JSON NOT NULL, \n\tconfiguration_evidence JSON NOT NULL, \n\tconfiguration_hash VARCHAR(64) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_revision PRIMARY KEY (id), \n\tCONSTRAINT fk_voucher_revision_3 FOREIGN KEY(tenant_id, company_id, class_id) REFERENCES voucher_class (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_revision_2 FOREIGN KEY(tenant_id, company_id, type_revision_id) REFERENCES voucher_type_revision (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_revision_1 FOREIGN KEY(tenant_id, company_id, voucher_id) REFERENCES voucher (tenant_id, company_id, id), \n\tCONSTRAINT uq_voucher_revision_tenant_id_company_id_voucher_id_revi_4f3b UNIQUE (tenant_id, company_id, voucher_id, revision_number), \n\tCONSTRAINT uq_voucher_revision_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_revision_0 (tenant_id, company_id, document_date, id),\n\tKEY ix_voucher_revision_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_revision")
