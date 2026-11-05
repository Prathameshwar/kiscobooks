"""create user_identity

Revision ID: 0015
Revises: 0014

Additional IdP links, so one person can sign in through Google or Microsoft as well as
Authentik without a second `user` row and a second set of role assignments
(docs/identity-schema.md §4.2).

Stores a **subject, never a credential**: no access token, no refresh token, no secret
(CLAUDE.md §5.9). A provider subject is a public identifier, so a leak of this table
authenticates nobody. Tokens we issue live in `user_api_token` (§4.4), hashed.

`uq_user_identity_provider_provider_sub` is the security-critical constraint here and is
**global, not per tenant**. Login arrives as `(provider, provider_sub)` and resolves to
a user; two rows sharing that pair would make one person's login resolve to either of
two accounts, across tenants. Both columns are NOT NULL, so §2's NULL problem does not
arise.

`provider_sub` is 255 because a provider's subject is opaque and some are long. It is
compared whole — never prefixed, never truncated — since a truncated subject could
match another user's.

Raw DDL for the reason given in revision 0001. Checklist: one DDL statement ·
ENGINE/CHARSET/COLLATE/ROW_FORMAT explicit · the composite unique is
40*4 + 255*4 + 2 = 1182 bytes, under 3072 (§1.6) · no NULL inside a unique key (§2) ·
no ENUM · no FLOAT · timestamps `DATETIME(6)` suffixed `_at` · no seed data · downgrade
present.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE TABLE user_identity (
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    provider VARCHAR(40) NOT NULL,
    provider_sub VARCHAR(255) NOT NULL,
    linked_at DATETIME(6) NOT NULL,
    last_login_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT pk_user_identity PRIMARY KEY (id),
    CONSTRAINT uq_user_identity_provider_provider_sub UNIQUE (provider, provider_sub),
    CONSTRAINT fk_user_identity_user_id FOREIGN KEY (user_id) REFERENCES `user` (id),
    KEY ix_user_identity_tenant_id (tenant_id),
    KEY ix_user_identity_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE user_identity")
