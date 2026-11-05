"""Original native invoice claim reference; one atomic ALTER per direction."""

from alembic import op

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE invoice_record "
        "ADD COLUMN source_invoice_id BINARY(16) NULL, "
        "ADD CONSTRAINT fk_invoice_record_source_invoice_id "
        "FOREIGN KEY (tenant_id, company_id, source_invoice_id) "
        "REFERENCES invoice_record (tenant_id, company_id, id), "
        "ADD CONSTRAINT source_kind CHECK "
        "((kind IN ('SALES','PURCHASE') AND source_invoice_id IS NULL) OR "
        "(kind IN ('CREDIT_NOTE','DEBIT_NOTE') AND source_invoice_id IS NOT NULL))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE invoice_record "
        "DROP CHECK source_kind, "
        "DROP FOREIGN KEY fk_invoice_record_source_invoice_id, "
        "DROP COLUMN source_invoice_id"
    )
