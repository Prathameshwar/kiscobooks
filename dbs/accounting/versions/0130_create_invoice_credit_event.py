"""invoice_credit_event; one atomic CREATE."""

from alembic import op

revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None

UPGRADE = "CREATE TABLE invoice_credit_event (\n\tinvoice_id BINARY(16) NOT NULL, \n\taction_id BINARY(16) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_invoice_credit_event PRIMARY KEY (id), \n\tCONSTRAINT fk_invoice_credit_event_action_id FOREIGN KEY(tenant_id, company_id, invoice_id, action_id) REFERENCES invoice_credit_action (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT uq_invoice_credit_event_tenant_id_company_id_action_id UNIQUE (tenant_id, company_id, action_id), \n\tCONSTRAINT uq_invoice_credit_event_tenant_id_company_id_invoice_id_id UNIQUE (tenant_id, company_id, invoice_id, id), \n\tCONSTRAINT fk_invoice_credit_event_invoice_id FOREIGN KEY(tenant_id, company_id, invoice_id) REFERENCES invoice_record (tenant_id, company_id, id), \n\tCONSTRAINT uq_invoice_credit_event_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\nINDEX ix_invoice_credit_event_tenant_id (tenant_id),\nINDEX ix_invoice_credit_event_history (tenant_id, company_id, invoice_id, id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute("DROP TABLE invoice_credit_event")
