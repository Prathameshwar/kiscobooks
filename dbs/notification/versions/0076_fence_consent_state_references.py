"""fence consent state references. One DDL statement per revision."""
from alembic import op
revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE consent_state ADD CONSTRAINT fk_consent_state_recipient_endpoint_id_space FOREIGN KEY(recipient_endpoint_id,
    tenant_id,
    space_id) REFERENCES recipient_endpoint (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE consent_state DROP FOREIGN KEY fk_consent_state_recipient_endpoint_id_space')
