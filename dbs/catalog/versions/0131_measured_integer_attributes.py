"""Permit native integer measurements consistently with the definition contract."""

from alembic import op

revision = "0131"
down_revision = "0130"
branch_labels = None
depends_on = None
_ALTER = """ALTER TABLE item_attribute_value
DROP CHECK ck_item_attribute_value_p76_scalar_type,
ADD CONSTRAINT ck_item_attribute_value_p76_scalar_type CHECK (option_id IS NOT NULL OR (
(value_type = 'TEXT' AND value_text IS NOT NULL AND unit_id IS NULL) OR
(value_type = 'INTEGER' AND value_integer IS NOT NULL) OR
(value_type = 'DECIMAL' AND value_decimal IS NOT NULL) OR
(value_type = 'BOOLEAN' AND value_boolean IS NOT NULL AND unit_id IS NULL) OR
(value_type = 'DATE' AND value_date IS NOT NULL AND unit_id IS NULL)))"""


def upgrade() -> None:
    op.execute(_ALTER)


def downgrade() -> None:
    raise RuntimeError("measured integer attributes must be migrated explicitly before downgrade")
