"""financial_opening_chunk: one atomic CREATE TABLE."""
from alembic import op
from sqlalchemy import text
revision = "0219"
down_revision = "0218"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
CREATE TABLE financial_opening_chunk (
    batch_id BINARY(16) NOT NULL,
    revision_id BINARY(16) NOT NULL,
    ordinal INTEGER NOT NULL,
    journal_id BINARY(16),
    payload JSON NOT NULL,
    company_id BINARY(16) NOT NULL,
    row_version INTEGER NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16),
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16),
    CONSTRAINT pk_financial_opening_chunk PRIMARY KEY (id),
    CONSTRAINT uq_fin_open_chunk_order UNIQUE (tenant_id, company_id, revision_id, ordinal),
    CONSTRAINT uq_fin_open_chunk_journal UNIQUE (tenant_id, company_id, journal_id),
    CONSTRAINT ck_financial_opening_chunk_fin_open_chunk_positive CHECK (ordinal > 0),
    CONSTRAINT uq_financial_opening_chunk_scope UNIQUE (tenant_id, company_id, id),
    CONSTRAINT ck_financial_opening_chunk_financial_opening_chunk_version CHECK (row_version > 0),
    CONSTRAINT fk_financial_opening_chunk_batch_id FOREIGN KEY(tenant_id, company_id, batch_id) REFERENCES opening_batch (tenant_id, company_id, id),
    CONSTRAINT fk_financial_opening_chunk_revision_id FOREIGN KEY(tenant_id, company_id, revision_id) REFERENCES financial_opening_revision (tenant_id, company_id, id),
    CONSTRAINT fk_financial_opening_chunk_journal_id FOREIGN KEY(tenant_id, company_id, journal_id) REFERENCES journal (tenant_id, company_id, id)
,
KEY ix_fin_open_chunk_batch (tenant_id, company_id, batch_id, id),
KEY ix_financial_opening_chunk_page (tenant_id, company_id, id),
KEY ix_financial_opening_chunk_tenant_id (tenant_id)
)ENGINE=InnoDB ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
""")

def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM financial_opening_chunk LIMIT 1")).first():
        raise RuntimeError("archive financial opening evidence before downgrade")
    op.execute("DROP TABLE financial_opening_chunk")
