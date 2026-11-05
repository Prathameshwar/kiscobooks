"""Add invoice_template.current_version_id foreign key once both tables exist.

Its own revision because the two tables reference each other and MySQL DDL is atomic per
statement but not transactional across statements (CLAUDE.md rule 4.8): a failure halfway
through a multi-statement revision would leave the schema and Alembic disagreeing.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADD = """
ALTER TABLE invoice_template
    ADD CONSTRAINT fk_invoice_template_current_version_id
    FOREIGN KEY (current_version_id) REFERENCES invoice_template_version (id) ON DELETE SET NULL
"""


def upgrade() -> None:
    op.execute(_ADD)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE invoice_template DROP FOREIGN KEY fk_invoice_template_current_version_id"
    )
