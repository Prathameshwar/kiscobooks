"""Create accounting_master_revision; exactly one DDL statement in each direction."""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE accounting_master_revision (\n\tentity_type VARCHAR(80) NOT NULL, \n\tobject_id BINARY(16) NOT NULL, \n\taction VARCHAR(20) NOT NULL, \n\tobject_version INTEGER NOT NULL, \n\tchanged_fields JSON NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_accounting_master_revision PRIMARY KEY (id),\n\tKEY ix_accounting_master_revision_tenant_id (tenant_id),\n\tKEY ix_accounting_revision_object (tenant_id, company_id, entity_type, object_id, id)\n)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE accounting_master_revision")
