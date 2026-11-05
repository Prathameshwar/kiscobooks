"""Index provider_account keyset lists under both ownership dimensions. One DDL."""
from alembic import op
revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE provider_account ADD KEY ix_provider_account_scoped_list_1 (`tenant_id`,
    `space_id`,
    `updated_at`,
    `id`),
    ADD KEY ix_provider_account_scoped_list_2 (`tenant_id`,
    `space_id`,
    `display_name`,
    `id`)
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE provider_account DROP INDEX ix_provider_account_scoped_list_1,
    DROP INDEX ix_provider_account_scoped_list_2
""")
