"""Index owner-scoped receipt discovery and keyset paging. One DDL."""
from alembic import op

revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE provider_event
        ADD INDEX ix_provider_event_scoped_list_1 (tenant_id,space_id,received_at,id),
        ADD INDEX ix_provider_event_scoped_list_2 (tenant_id,space_id,processing_status,received_at,id),
        ADD INDEX ix_provider_event_scoped_list_3 (tenant_id,space_id,provider_account_id,received_at,id)
    """)


def downgrade() -> None:
    op.execute("""ALTER TABLE provider_event
        DROP INDEX ix_provider_event_scoped_list_1,
        DROP INDEX ix_provider_event_scoped_list_2,
        DROP INDEX ix_provider_event_scoped_list_3
    """)
