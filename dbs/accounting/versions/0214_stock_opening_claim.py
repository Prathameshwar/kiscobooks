"""Immutable opening-cohort receipt with scoped owner references; one CREATE."""

from alembic import op
from sqlalchemy import text

revision = "0214"
down_revision = "0213"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE stock_opening_claim (
        control_id BINARY(16) NOT NULL, source_key VARCHAR(100) NOT NULL,
        posting_id BINARY(16) NOT NULL, movement_id BINARY(16) NOT NULL,
        currency VARCHAR(3) NOT NULL, company_id BINARY(16) NOT NULL,
        row_version INTEGER NOT NULL, id BINARY(16) NOT NULL, tenant_id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL, created_by BINARY(16),
        updated_at DATETIME(6) NOT NULL, updated_by BINARY(16),
        CONSTRAINT pk_stock_opening_claim PRIMARY KEY (id),
        CONSTRAINT uq_stock_opening_claim_scope UNIQUE (tenant_id, company_id, id),
        CONSTRAINT ck_stock_opening_claim_stock_opening_claim_version CHECK (row_version > 0),
        CONSTRAINT fk_stock_opening_claim_control FOREIGN KEY (tenant_id, company_id, control_id)
            REFERENCES stock_opening_control (tenant_id, company_id, id),
        CONSTRAINT fk_stock_opening_claim_posting FOREIGN KEY (tenant_id, company_id, posting_id)
            REFERENCES stock_posting (tenant_id, company_id, id),
        CONSTRAINT fk_stock_opening_claim_movement FOREIGN KEY (tenant_id, company_id, movement_id)
            REFERENCES stock_movement (tenant_id, company_id, id),
        CONSTRAINT uq_opening_claim_movement UNIQUE (tenant_id, company_id, movement_id),
        KEY ix_opening_claim_key (tenant_id, company_id, control_id, source_key, id),
        KEY ix_opening_claim_posting (tenant_id, company_id, posting_id, id),
        KEY ix_stock_opening_claim_page (tenant_id, company_id, id),
        KEY ix_stock_opening_claim_tenant_id (tenant_id)
    ) ENGINE=InnoDB CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COLLATE utf8mb4_unicode_ci""")


def downgrade() -> None:
    if op.get_bind().execute(text("SELECT id FROM stock_opening_claim LIMIT 1")).first():
        raise RuntimeError("archive retained opening receipts before downgrade")
    op.execute("DROP TABLE stock_opening_claim")
