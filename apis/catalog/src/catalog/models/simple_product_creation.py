"""Durable creation intent; balances remain owned by Accounting."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import JSON, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.configuration import ConfigurationRow


class SimpleProductCreation(ConfigurationRow):
    __tablename__ = "simple_product_creation"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "command_key", name="uq_simple_creation_key"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_simple_creation_code"),
        Index("ix_simple_creation_item", "tenant_id", "company_id", "item_id", "status"),
        CheckConstraint("status IN ('RUNNING','COMPLETE')", name="simple_creation_status"),
        CheckConstraint("row_version >= 1", name="simple_creation_version"),
        MARIADB_TABLE_ARGS,
    )
    command_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING")
    step: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATE")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
