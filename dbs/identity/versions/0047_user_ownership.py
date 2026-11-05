"""user ownership. One atomic DDL statement per direction.

Run tools/inventory_identity_integrity.py before upgrading a populated deployment.
Invalid historical rows are reported for explicit remediation; never deleted here.
"""
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE `user`
    ADD KEY ix_user_default_company_owner (tenant_id, default_company_id),
    ADD CONSTRAINT fk_user_default_company_owner FOREIGN KEY (tenant_id, default_company_id) REFERENCES company (tenant_id, id),
    ADD KEY ix_user_default_department_owner (tenant_id, default_company_id, default_department_id),
    ADD CONSTRAINT fk_user_default_department_owner FOREIGN KEY (tenant_id, default_company_id, default_department_id) REFERENCES department (tenant_id, company_id, id),
    ADD KEY ix_user_manager_owner (tenant_id, reporting_manager_id),
    ADD CONSTRAINT fk_user_manager_owner FOREIGN KEY (tenant_id, reporting_manager_id) REFERENCES `user` (tenant_id, id),
    ADD CONSTRAINT ck_user_default_department_requires_company CHECK (default_department_id IS NULL OR default_company_id IS NOT NULL)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE `user`
    DROP FOREIGN KEY fk_user_default_company_owner,
    DROP INDEX ix_user_default_company_owner,
    DROP FOREIGN KEY fk_user_default_department_owner,
    DROP INDEX ix_user_default_department_owner,
    DROP FOREIGN KEY fk_user_manager_owner,
    DROP INDEX ix_user_manager_owner,
    DROP CHECK ck_user_default_department_requires_company
""")
