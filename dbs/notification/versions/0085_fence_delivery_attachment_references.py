"""fence delivery attachment references. One DDL statement per revision."""
from alembic import op
revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attachment ADD CONSTRAINT fk_delivery_attachment_attachment_id_space FOREIGN KEY(attachment_id,
    tenant_id,
    space_id) REFERENCES attachment (id,
    tenant_id,
    space_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_delivery_attachment_delivery_id_space FOREIGN KEY(delivery_id,
    tenant_id,
    space_id) REFERENCES notification_delivery (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute("""
ALTER TABLE delivery_attachment DROP FOREIGN KEY fk_delivery_attachment_attachment_id_space,
    DROP FOREIGN KEY fk_delivery_attachment_delivery_id_space
""")
