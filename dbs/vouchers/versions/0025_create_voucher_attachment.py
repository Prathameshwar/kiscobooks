"""Create voucher_attachment; one DDL statement in each direction."""
from alembic import op

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_attachment (\n\trevision_id BINARY(16) NOT NULL, \n\tobject_key VARCHAR(200) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tmedia_type VARCHAR(60) NOT NULL, \n\tsize_bytes INTEGER NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_attachment PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_attachment_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id), \n\tCONSTRAINT fk_voucher_attachment_1 FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES voucher_revision (tenant_id, company_id, id),\n\tKEY ix_voucher_attachment_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_attachment")
