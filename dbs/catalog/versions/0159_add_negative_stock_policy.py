"""Add negative_stock_policy to inventory_profile_template_revision.

Allows configuring inventory behavior for stock deficits (BLOCK, WARN, ALLOW)
at the template level.
Defaults to 'BLOCK' to protect ledger and physical stock integrity.
"""

from alembic import op

revision = "0159"
down_revision = "0158"
branch_labels = None
depends_on = None

_ALTER = (
    "ALTER TABLE inventory_profile_template_revision "
    "ADD COLUMN negative_stock_policy VARCHAR(10) NOT NULL DEFAULT 'BLOCK', "
    "ADD CONSTRAINT ck_inventory_profile_template_revision_negative_stock "
    "CHECK (negative_stock_policy IN ('BLOCK','WARN','ALLOW'))"
)

def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE inventory_profile_template_revision "
        "DROP CHECK ck_inventory_profile_template_revision_negative_stock, "
        "DROP COLUMN negative_stock_policy"
    )
