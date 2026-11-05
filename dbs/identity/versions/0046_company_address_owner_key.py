"""company address owner key. One atomic DDL statement per direction.

Run tools/inventory_identity_integrity.py before upgrading a populated deployment.
Invalid historical rows are reported for explicit remediation; never deleted here.
"""
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE company_address
    ADD CONSTRAINT uq_company_address_owner_id UNIQUE (tenant_id, company_id, id)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE company_address
    DROP INDEX uq_company_address_owner_id
""")
