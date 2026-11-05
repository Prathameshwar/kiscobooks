"""Durable once-per-company cutover manifest; one atomic CREATE TABLE."""

from alembic import op
from sqlalchemy import text

revision = "0213"
down_revision = "0212"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_opening_control (
        books_begin_date DATE NOT NULL, status VARCHAR(16) NOT NULL,
        manifest JSON NOT NULL, manifest_hash VARCHAR(64) NOT NULL,
        finalized_at DATETIME(6), currency VARCHAR(3) NOT NULL,
        company_id BINARY(16) NOT NULL, row_version INTEGER NOT NULL,
        id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_stock_opening_control PRIMARY KEY (id),
        CONSTRAINT uq_stock_opening_control_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT ck_stock_opening_control_stock_opening_control_version CHECK (row_version > 0),
        CONSTRAINT uq_stock_opening_company UNIQUE (tenant_id, company_id),
        CONSTRAINT ck_stock_opening_control_stock_opening_status CHECK (status IN ('OPEN','FINALIZED')),
        CONSTRAINT ck_stock_opening_control_stock_opening_date CHECK (books_begin_date >= '1000-01-01'),
        KEY ix_stock_opening_control_page (tenant_id, company_id, id),
        KEY ix_stock_opening_control_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_opening_control LIMIT 1")).first():
        raise RuntimeError("archive retained opening manifests before downgrade")
    op.execute("DROP TABLE stock_opening_control")
