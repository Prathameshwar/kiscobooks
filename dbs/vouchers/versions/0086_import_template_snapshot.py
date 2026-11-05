"""Voucher import enhancement; one reversible DDL per direction."""
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

UP = 'CREATE TABLE import_template_snapshot (\n\tactor_user_id BINARY(16) NOT NULL, \n\tdefinition VARCHAR(40) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tsnapshot JSON, \n\texpires_at DATETIME(6) NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_import_template_snapshot PRIMARY KEY (id), \n\tCONSTRAINT uq_import_template_snapshot_scope UNIQUE (tenant_id, company_id, id),\n\tKEY ix_import_template_expiry (tenant_id, company_id, expires_at, id),\n\tKEY ix_import_template_snapshot_page (tenant_id, company_id, id),\n\tKEY ix_import_template_snapshot_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'
DOWN = 'DROP TABLE import_template_snapshot'

def upgrade() -> None:
    op.execute(UP)

def downgrade() -> None:
    op.execute(DOWN)
