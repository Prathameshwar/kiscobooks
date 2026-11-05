"""Independent source claims; one atomic ALTER with a legacy-compatible default."""
from alembic import op
from sqlalchemy import text

revision = "0190"
down_revision = "0189"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE stock_source_claim
        ADD COLUMN claim_type VARCHAR(16) NOT NULL DEFAULT 'RETURN',
        DROP INDEX uq_stock_source_claim_movement,
        ADD CONSTRAINT uq_stock_source_claim_type UNIQUE (tenant_id, company_id, movement_id, claim_type),
        ADD CONSTRAINT ck_stock_source_claim_stock_source_claim_type CHECK (claim_type IN ('RETURN','TRANSFER','INVOICE','REVERSAL'))""")


def downgrade() -> None:
    if op.get_bind().execute(text(
        "SELECT 1 FROM stock_source_claim WHERE claim_type <> 'RETURN' LIMIT 1"
    )).first():
        raise RuntimeError("retained typed stock claims require a forward repair")
    op.execute("""ALTER TABLE stock_source_claim
        DROP CHECK ck_stock_source_claim_stock_source_claim_type,
        DROP INDEX uq_stock_source_claim_type,
        ADD CONSTRAINT uq_stock_source_claim_movement UNIQUE (tenant_id, company_id, movement_id),
        DROP COLUMN claim_type""")
