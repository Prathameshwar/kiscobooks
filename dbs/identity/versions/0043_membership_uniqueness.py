"""membership uniqueness. One atomic DDL statement per direction.

Run tools/inventory_identity_integrity.py before upgrading a populated deployment.
Invalid historical rows are reported for explicit remediation; never deleted here.
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE membership
    ADD COLUMN department_scope_key BINARY(16) GENERATED ALWAYS AS (coalesce(department_id, X'00000000000000000000000000000000')) STORED,
    ADD COLUMN primary_user_id BINARY(16) GENERATED ALWAYS AS (CASE WHEN is_active = 1 AND is_primary = 1 THEN user_id ELSE NULL END) STORED,
    ADD CONSTRAINT uq_membership_affiliation UNIQUE (user_id, company_id, department_scope_key),
    ADD CONSTRAINT uq_membership_active_primary UNIQUE (primary_user_id)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE membership
    DROP INDEX uq_membership_affiliation,
    DROP INDEX uq_membership_active_primary,
    DROP COLUMN department_scope_key,
    DROP COLUMN primary_user_id
""")
