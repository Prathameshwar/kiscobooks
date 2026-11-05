"""create user_group_member

Revision ID: 0022
Revises: 0021

A user's membership of a group (docs/identity-schema.md §4.6). ``ix_..._user_id`` is the
resolution direction (given a user, its groups) and leads with the FK column; the unique
key leads with ``user_group_id`` and supports that FK. ``user`` is backticked — reserved
word. ``added_by`` carries no FK (§1.5).

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a
unique key · no ENUM · no FLOAT · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE user_group_member (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    user_group_id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    added_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_user_group_member PRIMARY KEY (id),
    CONSTRAINT uq_user_group_member_user_group_id_user_id UNIQUE (user_group_id, user_id),
    CONSTRAINT fk_user_group_member_user_group_id
        FOREIGN KEY (user_group_id) REFERENCES user_group (id),
    CONSTRAINT fk_user_group_member_user_id FOREIGN KEY (user_id) REFERENCES `user` (id),
    KEY ix_user_group_member_tenant_id (tenant_id),
    KEY ix_user_group_member_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE user_group_member")
