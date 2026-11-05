"""Create item_inventory_profile; one reversible DDL."""
from alembic import op

revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE item_inventory_profile (
	item_id BINARY(16) NOT NULL,
	base_unit_id BINARY(16) NOT NULL,
	template_revision_id BINARY(16) NOT NULL,
	identifier_profile_id BINARY(16) NULL,
	lot_tracking BOOL NOT NULL,
	serial_tracking BOOL NOT NULL,
	expiry_required BOOL NOT NULL,
	manufacture_date_required BOOL NOT NULL,
	shelf_life_days INTEGER NULL,
	minimum_remaining_life_days INTEGER NULL,
	issue_strategy VARCHAR(10) NOT NULL,
	valuation_method VARCHAR(20) NOT NULL,
	company_id BINARY(16) NOT NULL,
	row_version INTEGER NOT NULL,
	id BINARY(16) NOT NULL,
	tenant_id BINARY(16) NOT NULL,
	created_at DATETIME(6) NOT NULL,
	created_by BINARY(16) NULL,
	updated_at DATETIME(6) NOT NULL,
	updated_by BINARY(16) NULL,
	CONSTRAINT pk_item_inventory_profile PRIMARY KEY (id),
	CONSTRAINT uq_item_inventory_profile_scope UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_item_inventory_profile_version CHECK (row_version >= 1),
	CONSTRAINT uq_item_inventory_profile_item UNIQUE (tenant_id, company_id, item_id),
	CONSTRAINT fk_inventory_profile_item_id FOREIGN KEY(tenant_id, company_id, item_id) REFERENCES item (tenant_id, company_id, id),
	CONSTRAINT fk_inventory_profile_base_unit_id FOREIGN KEY(tenant_id, company_id, base_unit_id) REFERENCES unit_of_measure (tenant_id, company_id, id),
	CONSTRAINT fk_inventory_profile_template_revision_id FOREIGN KEY(tenant_id, company_id, template_revision_id) REFERENCES inventory_profile_template_revision (tenant_id, company_id, id),
	CONSTRAINT fk_inventory_profile_identifier_profile_id FOREIGN KEY(tenant_id, company_id, identifier_profile_id) REFERENCES identifier_profile (tenant_id, company_id, id),
	CONSTRAINT ck_item_inventory_profile_methods CHECK (issue_strategy IN ('FIFO','FEFO') AND valuation_method IN ('FIFO','MOVING_AVERAGE','SPECIFIC')),
	CONSTRAINT ck_item_inventory_profile_dates CHECK (lot_tracking = 1 OR (expiry_required = 0 AND manufacture_date_required = 0 AND shelf_life_days IS NULL AND minimum_remaining_life_days IS NULL)),
	CONSTRAINT ck_item_inventory_profile_expiry CHECK (expiry_required = 1 OR (issue_strategy <> 'FEFO' AND minimum_remaining_life_days IS NULL)),
	CONSTRAINT ck_item_inventory_profile_serial CHECK (serial_tracking = 1 OR (identifier_profile_id IS NULL AND valuation_method <> 'SPECIFIC')),
	CONSTRAINT ck_item_inventory_profile_shelf CHECK (shelf_life_days IS NULL OR shelf_life_days BETWEEN 1 AND 36500),
	CONSTRAINT ck_item_inventory_profile_remaining CHECK (minimum_remaining_life_days IS NULL OR (minimum_remaining_life_days BETWEEN 0 AND 36500 AND (shelf_life_days IS NULL OR minimum_remaining_life_days <= shelf_life_days))),
    INDEX ix_item_inventory_profile_tenant_id (tenant_id)
)CHARSET=utf8mb4 ENGINE=InnoDB ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci
"""

def upgrade() -> None:
    op.execute(_CREATE)

def downgrade() -> None:
    op.execute("DROP TABLE item_inventory_profile")
