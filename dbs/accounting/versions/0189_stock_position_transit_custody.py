"""Admit only typed internal transit alongside warehouse custody; one atomic ALTER."""
from alembic import op

revision = "0189"
down_revision = "0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE stock_position
        DROP CHECK ck_stock_position_stock_position_supported_scope,
        ADD CONSTRAINT ck_stock_position_stock_position_supported_scope CHECK (
            owner_kind = 'COMPANY' AND custody_kind IN ('WAREHOUSE','TRANSIT') AND disposition = 'USABLE'
        )""")


def downgrade() -> None:
    # Retained transit positions require a forward repair, never a silent deletion.
    op.execute("""ALTER TABLE stock_position
        DROP CHECK ck_stock_position_stock_position_supported_scope,
        ADD CONSTRAINT ck_stock_position_stock_position_supported_scope CHECK (
            owner_kind = 'COMPANY' AND custody_kind = 'WAREHOUSE' AND disposition = 'USABLE'
        )""")
