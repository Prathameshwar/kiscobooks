"""Create voucher_custom_sequence; one DDL statement in each direction."""
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

CREATE = 'CREATE TABLE voucher_custom_sequence (\n\tentity_type VARCHAR(40) NOT NULL, \n\tfield_key VARCHAR(64) NOT NULL, \n\tcycle_key VARCHAR(40) NOT NULL, \n\tnext_value BIGINT NOT NULL, \n\tcompany_id BINARY(16) NOT NULL, \n\trow_version INTEGER NOT NULL, \n\tid BINARY(16) NOT NULL, \n\ttenant_id BINARY(16) NOT NULL, \n\tcreated_at DATETIME(6) NOT NULL, \n\tcreated_by BINARY(16), \n\tupdated_at DATETIME(6) NOT NULL, \n\tupdated_by BINARY(16), \n\tCONSTRAINT pk_voucher_custom_sequence PRIMARY KEY (id), \n\tCONSTRAINT uq_voucher_custom_sequence_tenant_id_company_id_entity_t_4739 UNIQUE (tenant_id, company_id, entity_type, field_key, cycle_key), \n\tCONSTRAINT ck_voucher_custom_sequence_positive CHECK (next_value > 0), \n\tCONSTRAINT uq_voucher_custom_sequence_tenant_id_company_id_id UNIQUE (tenant_id, company_id, id),\n\tKEY ix_voucher_custom_sequence_tenant_id (tenant_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci'

def upgrade() -> None:
    op.execute(CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE voucher_custom_sequence")
