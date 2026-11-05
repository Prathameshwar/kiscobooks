"""Record the target reference separately from storage ownership. One DDL."""
from alembic import op
revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE notification_request ADD COLUMN target_tenant_id BINARY(16) NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE notification_request DROP COLUMN target_tenant_id")
