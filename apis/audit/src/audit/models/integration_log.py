from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class IntegrationLog(TenantMixin, Base):
    """Tracks inbound/outbound webhook deliveries, API errors, and exports."""

    __tablename__ = "integration_log"
    __table_args__ = (
        Index("ix_integration_log_tenant_id_occurred_at", "tenant_id", "occurred_at"),
        Index("ix_integration_log_tenant_id_integration_name", "tenant_id", "integration_name"),
        MARIADB_TABLE_ARGS,
    )

    #: Lead composite primary key for potential RANGE partition pruning, matching AuditEvent
    occurred_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid7, primary_key=True)

    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    integration_name: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # inbound | outbound
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failed | retrying
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
