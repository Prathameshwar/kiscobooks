"""Platform-owned public-registration projection and durable, immutable review intent."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import Boolean, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AccountReview(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "account_review"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_account_review_owner"),
        UniqueConstraint("tenant_id", "provider_uuid", name="uq_account_review_provider"),
        Index("ix_account_review_name", "tenant_id", "name", "id"),
        Index("ix_account_review_email", "tenant_id", "email", "id"),
        Index("ix_account_review_username", "tenant_id", "username", "id"),
        Index("ix_account_review_created", "tenant_id", "created_at", "id"),
        Index("ix_account_review_status", "tenant_id", "status", "created_at", "id"),
        MARIADB_TABLE_ARGS,
    )
    provider_uuid: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    provider_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    state_code: Mapped[str] = mapped_column(String(6), nullable=False)
    workspace_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    provider_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provider_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    needs_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AccountReviewCommand(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "account_review_command"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["account_review.tenant_id", "account_review.id"],
            name="fk_account_review_command_owner",
        ),
        UniqueConstraint(
            "tenant_id", "actor_id", "request_key", name="uq_account_review_command_key"
        ),
        Index("ix_account_review_command_history", "tenant_id", "account_id", "created_at", "id"),
        Index("ix_account_review_command_pending", "tenant_id", "status", "created_at", "id"),
        MARIADB_TABLE_ARGS,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    attested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    workspace_name: Mapped[str | None] = mapped_column(String(200))
    expected_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    error_code: Mapped[str | None] = mapped_column(String(40))
