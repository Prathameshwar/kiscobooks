"""Append-only native count evidence; one atomic CREATE."""

from alembic import op
from sqlalchemy import text

revision = "0223"
down_revision = "0222"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_count_observation (
	root_id BINARY(16) NOT NULL, 
	revision INTEGER NOT NULL, 
	item_id BINARY(16) NOT NULL, 
	base_unit_id BINARY(16) NOT NULL, 
	quantity_increment NUMERIC(19, 4) NOT NULL, 
	quantity_decimal_places INTEGER NOT NULL, 
	warehouse_id BINARY(16) NOT NULL, 
	bin_id BINARY(16), 
	lot_id BINARY(16), 
	stock_date DATE NOT NULL, 
	cutoff_at DATETIME(6) NOT NULL, 
	cutoff_generation BIGINT NOT NULL, 
	book_quantity NUMERIC(19, 4) NOT NULL, 
	observed_quantity NUMERIC(19, 4), 
	quantity_entry JSON, 
	reason VARCHAR(500) NOT NULL, 
	reviewed_unit_cost NUMERIC(19, 4), 
	cost_review_reason VARCHAR(500), 
	reviewed_pool_id BINARY(16), 
	reviewed_pool_version INTEGER, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_count_observation PRIMARY KEY (id), 
	CONSTRAINT uq_stock_count_observation_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_count_observation_stock_count_observation_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_count_revision UNIQUE (tenant_id, company_id, root_id, revision), 
	CONSTRAINT ck_stock_count_observation_stock_count_cutoff CHECK (revision > 0 AND cutoff_generation >= 0 AND book_quantity >= 0), 
	CONSTRAINT ck_stock_count_observation_stock_count_observed CHECK (observed_quantity IS NULL OR observed_quantity >= 0), 
	CONSTRAINT ck_stock_count_observation_stock_count_cost CHECK (reviewed_unit_cost IS NULL OR reviewed_unit_cost >= 0), 
	CONSTRAINT ck_stock_count_observation_stock_count_grid CHECK (quantity_increment > 0 AND quantity_decimal_places BETWEEN 0 AND 4),
	KEY ix_stock_count_grain (tenant_id, company_id, item_id, warehouse_id, id),
	KEY ix_stock_count_observation_page (tenant_id, company_id, id),
	KEY ix_stock_count_observation_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_count_observation LIMIT 1")).first():
        raise RuntimeError("archive retained count evidence before downgrade")
    op.execute("DROP TABLE stock_count_observation")
