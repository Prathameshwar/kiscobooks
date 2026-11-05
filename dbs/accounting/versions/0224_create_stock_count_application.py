"""Append-only native count evidence; one atomic CREATE."""

from alembic import op
from sqlalchemy import text

revision = "0224"
down_revision = "0223"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_count_application (
	root_id BINARY(16) NOT NULL, 
	observation_id BINARY(16) NOT NULL, 
	posting_id BINARY(16) NOT NULL, 
	difference NUMERIC(19, 4) NOT NULL, 
	later_quantity NUMERIC(19, 4) NOT NULL, 
	company_id BINARY(16) NOT NULL, 
	row_version INTEGER NOT NULL, 
	id BINARY(16) NOT NULL, 
	tenant_id BINARY(16) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	created_by BINARY(16), 
	updated_at DATETIME(6) NOT NULL, 
	updated_by BINARY(16), 
	CONSTRAINT pk_stock_count_application PRIMARY KEY (id), 
	CONSTRAINT uq_stock_count_application_scope UNIQUE (tenant_id, company_id, id), 
	CONSTRAINT ck_stock_count_application_stock_count_application_version CHECK (row_version > 0), 
	CONSTRAINT uq_stock_count_applied_root UNIQUE (tenant_id, company_id, root_id), 
	CONSTRAINT fk_stock_count_application_observation FOREIGN KEY(tenant_id, company_id, observation_id) REFERENCES stock_count_observation (tenant_id, company_id, id), 
	CONSTRAINT fk_stock_count_application_posting FOREIGN KEY(tenant_id, company_id, posting_id) REFERENCES stock_posting (tenant_id, company_id, id),
	KEY ix_stock_count_application_page (tenant_id, company_id, id),
	KEY ix_stock_count_application_tenant_id (tenant_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_count_application LIMIT 1")).first():
        raise RuntimeError("archive retained count evidence before downgrade")
    op.execute("DROP TABLE stock_count_application")
