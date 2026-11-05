"""user owner key. One atomic DDL statement per direction.

Run tools/inventory_identity_integrity.py before upgrading a populated deployment.
Invalid historical rows are reported for explicit remediation; never deleted here.
"""
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE `user`
    ADD CONSTRAINT uq_user_owner_id UNIQUE (tenant_id, id)
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE `user`
    DROP INDEX uq_user_owner_id
""")
