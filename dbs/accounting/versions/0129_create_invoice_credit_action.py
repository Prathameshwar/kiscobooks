"""invoice_credit_action; one atomic CREATE."""

from alembic import op

revision = "0129"
down_revision = "0128"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE invoice_credit_action (\n\tinvoice_id BINARY(16) NOT NULL, \n\tcomponent_id BINARY(16) NOT NULL, \n\texpected_event_id BINARY(16) NOT NULL, \n\tkind VARCHAR(24) NOT NULL, \n\tamount NUMERIC(19, 4) NOT NULL, \n\tevent_date DATE NOT NULL, \n\tposting_date DATE NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tjournal_id BINARY(16), \n\toffset_account_id BINARY(16), \n\tcash_deposit_line_id BINARY(16), \n\tannual_return_filed_on DATE, \n\tdocument_verified BOOL NOT NULL, \n\tsupply_received BOOL NOT NULL, \n\tbusiness_use BOOL NOT NULL, \n\trestrictions_checked BOOL NOT NULL, \n\tsupplier_report_matched BOOL NOT NULL, \n\ttax_payment_verified BOOL NOT NULL, \n\treturn_filed BOOL NOT NULL, \n\tsupplier_paid BOOL NOT NULL, \n\treference VARCHAR(500) NOT NULL, \n\tevidence_sha256 VARCHAR(64) NOT NULL, \n\treason VARCHAR(500) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_credit_action PRIMARY KEY (id), \n\tCONSTRAINT fk_invoice_credit_action_component_id FOREIGN KEY(tenant_id, company_id, invoice_id, component_id) REFERENCES invoice_tax_component (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_credit_action_journal_id FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id), \n\tCONSTRAINT fk_invoice_credit_action_offset_account_id FOREIGN KEY(tenant_id, company_id, offset_account_id) REFERENCES account (tenant_id, company_id, id), \n\tCONSTRAINT fk_invoice_credit_action_cash_deposit_line_id FOREIGN KEY(tenant_id, company_id, cash_deposit_line_id) REFERENCES journal_line (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_credit_action_tenant_id_company_id_journal_id UNIQUE (tenant_id, company_id, journal_id), \n\tCONSTRAINT ck_invoice_credit_action_amount CHECK (amount > 0), \n\tCONSTRAINT ck_invoice_credit_action_kind CHECK (kind IN ('VERIFY','CLAIM','BLOCK','REVERSE_PAYMENT','RECLAIM_PAYMENT','RCM_DISCHARGE')), \n\tCONSTRAINT ck_invoice_credit_action_evidence_hash CHECK (LENGTH(evidence_sha256) = 64), \n\tCONSTRAINT uq_invoice_credit_action_tenant_id_company_id_invoice_id_id UNIQUE (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_credit_action_invoice_id FOREIGN KEY(tenant_id, company_id, invoice_id) REFERENCES invoice_record (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_credit_action_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_credit_action_component (tenant_id, company_id, component_id, id),\nINDEX ix_invoice_credit_action_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_credit_action")
