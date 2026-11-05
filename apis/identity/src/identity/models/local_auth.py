"""Tables of the local authentication provider (docs/local-auth.md §5).

Installation-global on purpose: a sign-up exists before any tenant does, exactly as an Authentik
account does, so these rows carry no ``tenant_id`` and sit outside the tenant filter. They are
reachable only through ``identity.local_auth`` (and the adapters built on it); no tenant-scoped
route selects from them. Nothing here stores a password, a code or a token in the clear:
passwords are argon2id hashes, and every token, code and request id is kept as its SHA-256.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

#: ``status`` is this table's one lifecycle mechanism (rule 4.12): a pending sign-up, an account
#: that may sign in, or one that may not. Verification is the date beside it, not a second flag.
IDENTITY_STATUSES: Final = ("pending", "active", "disabled")
#: Where an identity sits, in the vocabulary the account-review state machine already speaks.
PATH_PENDING: Final = "bill/pending-registration"
PATH_ADMINISTRATORS: Final = "bill/tenant-administrators"
PATH_PLATFORM: Final = "bill/platform-administrator"
IDENTITY_PATHS: Final = (PATH_PENDING, PATH_ADMINISTRATORS, PATH_PLATFORM)
KEY_STATUSES: Final = ("active", "retiring", "retired")


class LocalIdentity(Base):
    """One person who can sign in with a local password."""

    __tablename__ = "local_identity"
    __table_args__ = (
        UniqueConstraint("uid", name="uq_local_identity_uid"),
        UniqueConstraint("sub", name="uq_local_identity_sub"),
        UniqueConstraint("email", name="uq_local_identity_email"),
        UniqueConstraint("username", name="uq_local_identity_username"),
        Index("ix_local_identity_path_status", "path", "status", "seq"),
        CheckConstraint(
            "status IN ('pending','active','disabled')", name=conv("ck_local_identity_status")
        ),
        MARIADB_TABLE_ARGS,
    )

    #: Doubles as the account-review ``provider_id`` (an integer), so the review workflow runs
    #: unchanged over local accounts.
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: The account-review ``provider_uuid``.
    uid: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: The token subject: 256 random bits as hex. Opaque, never derived from the email.
    sub: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Lower-cased by the code; the collation makes the unique key case-insensitive besides.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="")
    state_code: Mapped[str] = mapped_column(String(6), nullable=False, default="")
    workspace_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    path: Mapped[str] = mapped_column(String(40), nullable=False, default=PATH_PENDING)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    email_verified_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    #: The account-review command that last activated or rejected this identity, so a lost
    #: response is reconciled without repeating the write.
    review_command: Mapped[str | None] = mapped_column(String(36), nullable=True)
    #: The tenant-administrator provisioning command that created it.
    provision_command: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class LocalCredential(Base):
    """The password of one identity, and what is needed to defend it."""

    __tablename__ = "local_credential"
    __table_args__ = (MARIADB_TABLE_ARGS,)

    identity_seq: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("local_identity.seq", name="fk_local_credential_identity"),
        primary_key=True,
    )
    #: argon2id in its self-describing encoded form (parameters and salt included).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    lock_ends_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class LocalRecoveryToken(IdMixin, Base):
    """A one-time password-recovery link, held only as the SHA-256 of its token."""

    __tablename__ = "local_recovery_token"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_local_recovery_token_hash"),
        Index("ix_local_recovery_token_identity", "identity_seq", "expires_at"),
        MARIADB_TABLE_ARGS,
    )

    identity_seq: Mapped[int] = mapped_column(
        Integer, ForeignKey("local_identity.seq", name="fk_local_recovery_identity"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The user who asked for the link, for the audit trail; ``None`` for a bootstrap issue.
    issued_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class LocalSigningKey(Base):
    """An RS256 signing key. The private half exists only encrypted, bound to its ``kid``."""

    __tablename__ = "local_signing_key"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','retiring','retired')", name=conv("ck_local_signing_key_status")
        ),
        MARIADB_TABLE_ARGS,
    )

    kid: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    public_jwk: Mapped[str] = mapped_column(Text, nullable=False)
    #: Base64 of AES-256-GCM(nonce || ciphertext), associated data = the ``kid``.
    private_jwk_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    #: When it stopped signing. Its public half is published until its last token has expired.
    retired_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class LocalAuthorization(Base):
    """An authorization request, and — once the person has signed in — its one-use code."""

    __tablename__ = "local_authorization"
    __table_args__ = (
        UniqueConstraint("code_hash", name="uq_local_authorization_code"),
        Index("ix_local_authorization_expiry", "expires_at"),
        MARIADB_TABLE_ARGS,
    )

    #: SHA-256 of the request id the browser carries to the sign-in page.
    request_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    scope: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(512), nullable=False)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(43), nullable=False)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    #: The request's own lifetime until sign-in; after it, the code's.
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    identity_seq: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("local_identity.seq", name="fk_local_authorization_identity"),
        nullable=True,
    )
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authenticated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    #: The refresh family a redeemed code started, so a replayed code can revoke it.
    family_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class LocalRefreshToken(IdMixin, Base):
    """A refresh token, held as its SHA-256. Rotation links tokens through ``family_id``."""

    __tablename__ = "local_refresh_token"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_local_refresh_token_hash"),
        Index("ix_local_refresh_token_family", "family_id"),
        Index("ix_local_refresh_token_identity", "identity_seq"),
        MARIADB_TABLE_ARGS,
    )

    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_seq: Mapped[int] = mapped_column(
        Integer, ForeignKey("local_identity.seq", name="fk_local_refresh_identity"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(512), nullable=False)
    #: The original sign-in. Preserved across refresh so `auth_time` means what it says.
    authenticated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    #: Set when the token is exchanged. Presenting it again is the theft signal.
    rotated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
