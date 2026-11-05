"""Optional classification references; existing companies stay unclassified.

One ALTER per direction. No backfill guesses a company's industry or roles.
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE company
    ADD COLUMN business_category_code VARCHAR(32) NULL,
    ADD COLUMN store_format_code VARCHAR(32) NULL,
    ADD CONSTRAINT uq_company_tenant_id_id UNIQUE (tenant_id, id),
    ADD KEY ix_company_business_category_code (business_category_code),
    ADD KEY ix_company_store_format_code (store_format_code),
    ADD CONSTRAINT fk_company_business_category_code FOREIGN KEY (business_category_code)
        REFERENCES business_category (code),
    ADD CONSTRAINT fk_company_store_format_code FOREIGN KEY (store_format_code)
        REFERENCES store_format (code)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE company
    DROP FOREIGN KEY fk_company_business_category_code,
    DROP FOREIGN KEY fk_company_store_format_code,
    DROP INDEX ix_company_business_category_code,
    DROP INDEX ix_company_store_format_code,
    DROP INDEX uq_company_tenant_id_id,
    DROP COLUMN business_category_code,
    DROP COLUMN store_format_code
""")
