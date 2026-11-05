"""Configure the existing model code without changing historical product settings."""

from alembic import context, op
from sqlalchemy import text

revision = "0217"
down_revision = "0216"
branch_labels = None
depends_on = None


_ALTER = """
ALTER TABLE product_entry_option_policy
    ADD COLUMN model_mode VARCHAR(10) NOT NULL DEFAULT 'INHERIT',
    ADD COLUMN model_default BOOLEAN NULL,
    ADD CONSTRAINT ck_product_entry_option_policy_entry_model_mode
        CHECK (model_mode IN ('INHERIT','DISABLED','OPTIONAL','REQUIRED') AND
            ((model_mode = 'OPTIONAL' AND model_default IS NOT NULL) OR
             (model_mode <> 'OPTIONAL' AND model_default IS NULL)))
"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("model-option rollback requires online validation of history")
    authored = (
        op.get_bind()
        .execute(
            text(
                "SELECT 1 FROM product_entry_option_policy "
                "WHERE model_mode <> 'INHERIT' OR model_default IS NOT NULL LIMIT 1"
            )
        )
        .first()
    )
    if authored is not None:
        raise RuntimeError("cannot discard authored model-option settings")
    op.execute("""
ALTER TABLE product_entry_option_policy
    DROP CHECK ck_product_entry_option_policy_entry_model_mode,
    DROP COLUMN model_default,
    DROP COLUMN model_mode
""")
