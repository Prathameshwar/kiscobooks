"""Native tax-component GL lineage; one atomic ALTER per direction."""

from alembic import op

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE invoice_posting_line "
        "ADD COLUMN tax_component_id BINARY(16) NULL, "
        "ADD COLUMN tax_purpose VARCHAR(30) NULL, "
        "ADD CONSTRAINT fk_invoice_posting_line_tax_component_id "
        "FOREIGN KEY (tenant_id, company_id, invoice_id, tax_component_id) "
        "REFERENCES invoice_tax_component (tenant_id, company_id, invoice_id, id)"
    )


def downgrade() -> None:
    # Removes supplementary linkage only; native tax and GL facts remain intact.
    op.execute(
        "ALTER TABLE invoice_posting_line "
        "DROP FOREIGN KEY fk_invoice_posting_line_tax_component_id, "
        "DROP COLUMN tax_purpose, DROP COLUMN tax_component_id"
    )
