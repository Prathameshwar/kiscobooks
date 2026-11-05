"""company tax registration ownership. One atomic DDL statement per direction.

Run tools/inventory_identity_integrity.py before upgrading a populated deployment.
Invalid historical rows are reported for explicit remediation; never deleted here.
"""
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE company_tax_registration
    ADD KEY ix_company_tax_registration_address_owner (tenant_id, company_id, registered_address_id),
    ADD CONSTRAINT fk_company_tax_registration_address_owner FOREIGN KEY (tenant_id, company_id, registered_address_id) REFERENCES company_address (tenant_id, company_id, id)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE company_tax_registration
    DROP FOREIGN KEY fk_company_tax_registration_address_owner,
    DROP INDEX ix_company_tax_registration_address_owner
""")
