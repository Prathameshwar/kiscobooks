"""create impersonation_session

Revision ID: 0029
Revises: 0028

A time-bound, audited support impersonation (docs/identity-schema.md §4.8).
``actor_user_id``/``target_user_id`` carry no FK (§4.8 Keys). The
``(ended_at, expires_at)`` index serves the sweeper that closes expired sessions.

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no ENUM · no
FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data · downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE impersonation_session (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    actor_user_id BINARY(16) NOT NULL,
    target_user_id BINARY(16) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    ticket_reference VARCHAR(120) NULL,
    started_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6) NULL,
    ended_reason VARCHAR(40) NULL,
    actor_ip VARCHAR(45) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_impersonation_session PRIMARY KEY (id),
    KEY ix_impersonation_session_tenant_id (tenant_id),
    KEY ix_impersonation_session_target_user_id_ended_at (target_user_id, ended_at),
    KEY ix_impersonation_session_ended_at_expires_at (ended_at, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE impersonation_session")
