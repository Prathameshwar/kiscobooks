"""fence notification content references. One DDL statement per revision."""
from alembic import op
revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE notification_content ADD CONSTRAINT fk_notification_content_delivery_id_space FOREIGN KEY(delivery_id,
    tenant_id,
    space_id) REFERENCES notification_delivery (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE notification_content DROP FOREIGN KEY fk_notification_content_delivery_id_space')
