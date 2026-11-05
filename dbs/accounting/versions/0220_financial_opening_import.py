"""financial_opening_import: one atomic CREATE TABLE."""
from alembic import op
from sqlalchemy import text
revision = "0220"
down_revision = "0219"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE financial_opening_import (
    source_key VARCHAR(100) NOT NULL,
    input_hash VARCHAR(64) NOT NULL,
    state VARCHAR(30) NOT NULL,
    batch_id BINARY(16),
    review_hash VARCHAR(64),
    document JSON NOT NULL,
    issues JSON NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_financial_opening_import PRIMARY KEY (id),
    CONSTRAINT uq_fin_open_import_source UNIQUE (tenant_id, company_id, source_key),
    CONSTRAINT ck_financial_opening_import_fin_open_import_state CHECK (state IN ('STAGED','READY','COMMITTED','BLOCKED','CANCELLED')),
    CONSTRAINT uq_financial_opening_import_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_financial_opening_import_financial_opening_import_version CHECK (row_version > 0),
    CONSTRAINT fk_financial_opening_import_batch_id FOREIGN KEY(tenant_id, company_id, batch_id) REFERENCES opening_batch (tenant_id, company_id, id)
,
KEY ix_fin_open_import_hash (tenant_id, company_id, input_hash, id),
KEY ix_fin_open_import_state (tenant_id, company_id, state, id),
KEY ix_financial_opening_import_page (tenant_id, company_id, id),
KEY ix_financial_opening_import_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM financial_opening_import LIMIT 1")).first():
        raise RuntimeError("archive financial opening evidence before downgrade")
    op.execute("DROP TABLE financial_opening_import")
