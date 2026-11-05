"""create user_api_token

Revision ID: 0028
Revises: 0027

A personal access token (docs/identity-schema.md §4.4). The raw token is never stored:
only ``token_hash`` (SHA-256) and ``token_prefix``. Lifecycle is ``revoked_at`` +
``expires_at`` (rule 4.12), not ``is_active``. ``token_hash`` is globally unique — a
presented token resolves by its hash alone. ``revoked_by`` carries no FK (§1.5). ``user``
is backticked — reserved word.

Checklist: one DDL statement · ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · no NULL in a
unique key · no ENUM · no FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data ·
downgrade present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE user_api_token (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    name VARCHAR(120) NOT NULL,
    token_prefix VARCHAR(12) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    scopes JSON NULL,
    last_used_at DATETIME(6) NULL,
    last_used_ip VARCHAR(45) NULL,
    expires_at DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    revoked_by BINARY(16) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_user_api_token PRIMARY KEY (id),
    CONSTRAINT uq_user_api_token_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_user_api_token_user_id FOREIGN KEY (user_id) REFERENCES `user` (id),
    KEY ix_user_api_token_tenant_id (tenant_id),
    KEY ix_user_api_token_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE user_api_token")
