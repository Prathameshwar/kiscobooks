"""Retain scoped warehouse-retirement write fences; one atomic CREATE."""

from alembic import op
from sqlalchemy import text

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_retirement_fence (
        check_id BINARY(16) NOT NULL,
        actor_user_id BINARY(16) NOT NULL,
        warehouse_id BINARY(16) NOT NULL,
        bin_id BINARY(16),
        request_hash VARCHAR(64) NOT NULL,
        expires_at DATETIME(6) NOT NULL,
        closed_at DATETIME(6),
        company_id BINARY(16) NOT NULL,
        row_version INTEGER NOT NULL,
        id BINARY(16) NOT NULL,
        tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL,
        created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL,
        updated_by BINARY(16),
        CONSTRAINT pk_stock_retirement_fence PRIMARY KEY (id),
        CONSTRAINT uq_stock_retirement_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT uq_stock_retirement_check UNIQUE (tenant_id, company_id, check_id),
        CONSTRAINT fk_stock_retirement_company FOREIGN KEY (tenant_id, company_id)
            REFERENCES voucher_company_guard (tenant_id, company_id),
        CONSTRAINT ck_stock_retirement_fence_stock_retirement_lifetime
            CHECK (row_version > 0 AND expires_at > created_at),
        KEY ix_stock_retirement_live (tenant_id, company_id, closed_at, expires_at, id),
        KEY ix_stock_retirement_fence_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_retirement_fence LIMIT 1")).first():
        raise RuntimeError("retained retirement evidence requires a reviewed archive before downgrade")
    op.execute("DROP TABLE stock_retirement_fence")
