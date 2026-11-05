"""fence delivery event references. One DDL statement per revision."""
from alembic import op
revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE delivery_event ADD CONSTRAINT fk_delivery_event_delivery_id_space FOREIGN KEY(delivery_id,
    tenant_id,
    space_id) REFERENCES notification_delivery (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE delivery_event DROP FOREIGN KEY fk_delivery_event_delivery_id_space')
