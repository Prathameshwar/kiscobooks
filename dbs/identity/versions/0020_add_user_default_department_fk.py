"""add user.default_department_id foreign key

Revision ID: 0020
Revises: 0019

The one deferred constraint, resolved (docs/identity-db-plan.md §6). Revision 0014
created ``user.default_department_id`` without a foreign key because ``department`` did
not exist until revision 0019 — the cyclic dependency the plan §1.5 describes.

**One ``ALTER TABLE``, two clauses.** InnoDB needs an index leading with the FK column
or it invents one named after the constraint (invisible in the model, reads as
autogenerate drift forever). Adding the index and the FK in a single ``ALTER TABLE`` is
still one DDL statement (rule 4.8 / §1.1), so the index gets the name the model declares
(``ix_user_default_department_id``) rather than InnoDB's.

``user`` is backticked — reserved word.

Checklist: one DDL statement per direction · no ENUM · no FLOAT · no seed data ·
downgrade present (drops the FK then the index, the reverse order).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE = """
ALTER TABLE `user`
    ADD KEY ix_user_default_department_id (default_department_id),
    ADD CONSTRAINT fk_user_default_department_id
        FOREIGN KEY (default_department_id) REFERENCES department (id)
"""

_DOWNGRADE = """
ALTER TABLE `user`
    DROP FOREIGN KEY fk_user_default_department_id,
    DROP KEY ix_user_default_department_id
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    op.execute(_DOWNGRADE)
