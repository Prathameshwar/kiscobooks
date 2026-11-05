"""Immutable indexed shipment destinations; one reversible CREATE."""

from alembic import op
import sqlalchemy as sa

revision = "0200"
down_revision = "0199"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_posting WHERE action = 'TRANSFER_DISPATCH' LIMIT 1")):
        raise RuntimeError("Existing shipments require a reviewed destination backfill before this migration")
    op.execute("""CREATE TABLE stock_transfer_destination (
	transit_movement_id BINARY(16) NOT NULL, 
	destination_position_id BINARY(16) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_transfer_destination PRIMARY KEY (id), 
	CONSTRAINT uq_stock_transfer_destination_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_transfer_destination_stock_transfer_destination_version CHECK (row_version > 0), 
	CONSTRAINT fk_stock_transfer_destination_move FOREIGN KEY(tenant_id, company_id, transit_movement_id) REFERENCES stock_movement (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_transfer_destination_pos FOREIGN KEY(tenant_id, company_id, destination_position_id) REFERENCES stock_position (tenant_id, company_id, id), 
	CONSTRAINT uq_stock_transfer_destination_move UNIQUE (tenant_id, company_id, transit_movement_id),
	KEY ix_stock_transfer_destination_page (tenant_id, company_id, id),
	KEY ix_stock_transfer_destination_target (tenant_id, company_id, destination_position_id, id),
	KEY ix_stock_transfer_destination_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM stock_transfer_destination LIMIT 1")):
        raise RuntimeError("Retained shipment destinations prevent downgrade")
    op.execute("DROP TABLE stock_transfer_destination")
