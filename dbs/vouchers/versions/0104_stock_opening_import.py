"""Durable bounded opening import workflow metadata; one CREATE TABLE."""

from alembic import op
from sqlalchemy import text

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_opening_import (
        source_key VARCHAR(100) NOT NULL, input_hash VARCHAR(64) NOT NULL,
        payload JSON NOT NULL, state VARCHAR(20) NOT NULL,
        review JSON NOT NULL, effects JSON NOT NULL, errors JSON NOT NULL,
        reviewed_authority VARCHAR(64), review_hash VARCHAR(64), expires_at DATETIME(6) NOT NULL,
        company_id BINARY(16) NOT NULL, row_version INTEGER NOT NULL,
        id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_stock_opening_import PRIMARY KEY (id),
        CONSTRAINT uq_stock_opening_import_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT uq_stock_opening_import_source UNIQUE (tenant_id, company_id, source_key),
        CONSTRAINT uq_opening_import_input UNIQUE (tenant_id, company_id, input_hash),
        CONSTRAINT ck_stock_opening_import_opening_import_state
            CHECK (state IN ('STAGED','VALIDATING','READY','COMMITTING','DRAFTS_CREATED','BLOCKED','CANCELLED')),
        CONSTRAINT ck_stock_opening_import_opening_import_version CHECK (row_version > 0),
        KEY ix_stock_opening_import_page (tenant_id, company_id, id),
        KEY ix_stock_opening_import_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_opening_import LIMIT 1")).first():
        raise RuntimeError("archive retained opening import evidence before downgrade")
    op.execute("DROP TABLE stock_opening_import")
