"""fence sender identity references. One DDL statement per revision."""
from alembic import op
revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
ALTER TABLE sender_identity ADD CONSTRAINT fk_sender_identity_provider_account_id_space FOREIGN KEY(provider_account_id,
    tenant_id,
    space_id) REFERENCES provider_account (id,
    tenant_id,
    space_id) ON DELETE RESTRICT
""")

def downgrade() -> None:
    op.execute('ALTER TABLE sender_identity DROP FOREIGN KEY fk_sender_identity_provider_account_id_space')
