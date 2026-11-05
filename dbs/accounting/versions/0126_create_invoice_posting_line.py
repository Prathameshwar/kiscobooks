"""invoice_posting_line; one atomic CREATE."""
from alembic import op

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE invoice_posting_line (\n\tinvoice_id BINARY(16) NOT NULL, \n\tjournal_line_id BINARY(16) NOT NULL, \n\tline_key BINARY(16) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tsource_version INTEGER NOT NULL, \n\tpurpose VARCHAR(20) NOT NULL, \n\ttracking VARCHAR(20) NOT NULL, \n\tbill_reference VARCHAR(120), \n\tdue_date DATE, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_posting_line PRIMARY KEY (id), \n\tCONSTRAINT fk_invoice_posting_line_journal_line_id FOREIGN KEY(tenant_id, company_id, journal_line_id) REFERENCES journal_line (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_posting_line_tenant_id_company_id_invoice_id_line_key UNIQUE (tenant_id, company_id, invoice_id, line_key), \n\tCONSTRAINT uq_invoice_posting_line_tenant_id_company_id_journal_line_id UNIQUE (tenant_id, company_id, journal_line_id), \n\tCONSTRAINT ck_invoice_posting_line_version_sequence CHECK (source_version > 0 AND sequence > 0), \n\tCONSTRAINT ck_invoice_posting_line_tracking CHECK (tracking IN ('NONE','NEW_REF','ON_ACCOUNT','ADVANCE')), \n\tCONSTRAINT uq_invoice_posting_line_tenant_id_company_id_invoice_id_id UNIQUE (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_posting_line_invoice_id FOREIGN KEY(tenant_id, company_id, invoice_id) REFERENCES invoice_record (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_posting_line_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_posting_line_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"

def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_posting_line")
