"""Durable submitted product definition and later native-owner progress."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import JSON, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.configuration import ConfigurationRow


class AdvancedProductCreation(ConfigurationRow):
    __tablename__ = "advanced_product_creation"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "owner_user_id",
            "command_key",
            name="uq_advanced_product_creation_key",
        ),
        Index(
            "ix_advanced_product_creation_owner", "tenant_id", "company_id", "owner_user_id", "id"
        ),
        CheckConstraint("row_version >= 1", name="advanced_product_creation_version"),
        CheckConstraint(
            "status IN ('DEFINED','SETUP','ACTIVATING','OPENING','COMPLETE')",
            name="advanced_product_creation_status",
        ),
        MARIADB_TABLE_ARGS,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    command_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DEFINED")
    step: Mapped[str] = mapped_column(String(32), nullable=False, default="SETUP")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sku_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
