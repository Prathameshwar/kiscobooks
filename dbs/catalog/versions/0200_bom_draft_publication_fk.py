"""Link a frozen draft to its publication; one reversible DDL."""
from alembic import op

revision = "0200"
down_revision = "0199"
branch_labels = None
depends_on = None

_ALTER = """
ALTER TABLE bom_draft ADD CONSTRAINT fk_bom_draft_publication FOREIGN KEY(tenant_id, company_id, published_revision_id) REFERENCES bom_revision (tenant_id, company_id, id)
"""

def upgrade() -> None:
    op.execute(_ALTER)

def downgrade() -> None:
    op.execute("ALTER TABLE bom_draft DROP FOREIGN KEY fk_bom_draft_publication")
