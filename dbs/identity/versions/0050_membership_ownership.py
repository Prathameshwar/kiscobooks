"""membership ownership. One atomic DDL statement per direction.

Run tools/inventory_identity_integrity.py before upgrading a populated deployment.
Invalid historical rows are reported for explicit remediation; never deleted here.
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE membership
    ADD KEY ix_membership_user_owner (tenant_id, user_id),
    ADD CONSTRAINT fk_membership_user_owner FOREIGN KEY (tenant_id, user_id) REFERENCES `user` (tenant_id, id),
    ADD KEY ix_membership_company_owner (tenant_id, company_id),
    ADD CONSTRAINT fk_membership_company_owner FOREIGN KEY (tenant_id, company_id) REFERENCES company (tenant_id, id),
    ADD KEY ix_membership_department_owner (tenant_id, company_id, department_id),
    ADD CONSTRAINT fk_membership_department_owner FOREIGN KEY (tenant_id, company_id, department_id) REFERENCES department (tenant_id, company_id, id)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE membership
    DROP FOREIGN KEY fk_membership_user_owner,
    DROP INDEX ix_membership_user_owner,
    DROP FOREIGN KEY fk_membership_company_owner,
    DROP INDEX ix_membership_company_owner,
    DROP FOREIGN KEY fk_membership_department_owner,
    DROP INDEX ix_membership_department_owner
""")
