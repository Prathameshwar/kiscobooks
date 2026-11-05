"""Allow audited retention scrub of original request variables. One DDL."""
from alembic import op
revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE notification_request MODIFY COLUMN context_ciphertext MEDIUMBLOB NULL")

def downgrade() -> None:
    # Cannot reconstruct cryptographically purged evidence. Refuse rather than fabricate it.
    op.execute("ALTER TABLE notification_request MODIFY COLUMN context_ciphertext MEDIUMBLOB NOT NULL")
