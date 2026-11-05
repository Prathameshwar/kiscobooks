"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}

One DDL statement (rule 4.8, docs/identity-db-plan.md §1.1). ENGINE, CHARSET,
COLLATE and ROW_FORMAT explicit. `tenant_id` leads every composite index on a
tenant-scoped table. No NULL inside a UNIQUE key — SCOPE_ALL instead. No seed
data here; seeds live in `seeds/`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
