"""Restartable ownership backfill. No DDL; quiesce legacy writers before upgrade.
Each bounded UPDATE commits independently, so interruption never holds a whole
history table locked or requires the batch to be restarted from scratch.
"""
from alembic import op
from sqlalchemy import text
revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None
_TABLES = ('attachment', 'notification_preference', 'notification_request', 'notification_template', 'party_endpoint_checkpoint', 'provider_account', 'recipient_endpoint', 'voucher_send_state', 'consent_event', 'consent_state', 'sender_identity', 'suppression', 'template_variant', 'routing_rule', 'template_version', 'provider_template_binding', 'template_activation', 'notification_delivery', 'delivery_attachment', 'delivery_attempt', 'delivery_event', 'notification_content', 'provider_event')

def upgrade() -> None:
    # Identifiers are the literal migration inventory above, never request input.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        for table in _TABLES:
            while True:
                result = bind.execute(text(f"UPDATE `{table}` SET space_id=tenant_id WHERE space_id IS NULL LIMIT 1000"))
                if result.rowcount < 1000:
                    break
            bind.execute(text(f"INSERT IGNORE INTO notification_space (id,tenant_id,kind,created_at) SELECT DISTINCT tenant_id,tenant_id,'tenant',UTC_TIMESTAMP(6) FROM `{table}`"))

def downgrade() -> None:
    # Preserve backfilled ownership until the corresponding columns are removed.
    pass
