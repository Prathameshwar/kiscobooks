"""fence consent event references. One DDL statement per revision."""
from alembic import op
revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE consent_event ADD CONSTRAINT fk_consent_event_recipient_endpoint_id_space FOREIGN KEY(recipient_endpoint_id,
    tenant_id,
    space_id) REFERENCES recipient_endpoint (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE consent_event DROP FOREIGN KEY fk_consent_event_recipient_endpoint_id_space')
