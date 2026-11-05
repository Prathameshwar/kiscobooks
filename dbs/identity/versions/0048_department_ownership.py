"""department ownership. One atomic DDL statement per direction.

Run tools/inventory_identity_integrity.py before upgrading a populated deployment.
Invalid historical rows are reported for explicit remediation; never deleted here.
"""
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE department
    ADD KEY ix_department_head_owner (tenant_id, head_user_id),
    ADD CONSTRAINT fk_department_head_owner FOREIGN KEY (tenant_id, head_user_id) REFERENCES `user` (tenant_id, id),
    ADD KEY ix_department_company_owner (tenant_id, company_id),
    ADD CONSTRAINT fk_department_company_owner FOREIGN KEY (tenant_id, company_id) REFERENCES company (tenant_id, id),
    ADD KEY ix_department_parent_owner (tenant_id, company_id, parent_id),
    ADD CONSTRAINT fk_department_parent_owner FOREIGN KEY (tenant_id, company_id, parent_id) REFERENCES department (tenant_id, company_id, id)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE department
    DROP FOREIGN KEY fk_department_head_owner,
    DROP INDEX ix_department_head_owner,
    DROP FOREIGN KEY fk_department_company_owner,
    DROP INDEX ix_department_company_owner,
    DROP FOREIGN KEY fk_department_parent_owner,
    DROP INDEX ix_department_parent_owner
""")
