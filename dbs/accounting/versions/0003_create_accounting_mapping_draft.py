"""Create accounting_mapping_draft; exactly one DDL statement in each direction."""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE accounting_mapping_draft (\n\t`values` JSON NOT NULL, \n\tpublished_mapping_id BINARY(16), \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_accounting_mapping_draft PRIMARY KEY (id),\n\tKEY ix_accounting_mapping_draft_page (tenant_id, company_id, id),\n\tKEY ix_accounting_mapping_draft_tenant_id (tenant_id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE accounting_mapping_draft")
