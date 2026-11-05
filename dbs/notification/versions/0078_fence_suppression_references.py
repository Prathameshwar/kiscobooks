"""fence suppression references. One DDL statement per revision."""
from alembic import op
revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE suppression ADD CONSTRAINT fk_suppression_recipient_endpoint_id_space FOREIGN KEY(recipient_endpoint_id,
    tenant_id,
    space_id) REFERENCES recipient_endpoint (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE suppression DROP FOREIGN KEY fk_suppression_recipient_endpoint_id_space')
