"""Durable, company-scoped initialization and report enrollment evidence."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import JSON, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CompanySetupRun(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "company_setup_run"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", name="uq_company_setup_company"),
        UniqueConstraint("tenant_id", "command_key", name="uq_company_setup_command"),
        ForeignKeyConstraint(["tenant_id", "company_id"], ["company.tenant_id", "company.id"]),
        Index("ix_company_setup_pending", "status", "available_at", "id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    command_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    opening_choice: Mapped[str] = mapped_column(String(20), nullable=False, default="DECIDE_LATER")
    opening_reason: Mapped[str | None] = mapped_column(String(500))
    requested_features: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    available_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(60))


class CompanySetupStep(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "company_setup_step"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "key", name="uq_company_setup_step"),
        ForeignKeyConstraint(["tenant_id", "company_id"], ["company.tenant_id", "company.id"]),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(60))


class ReportSourceEnrollment(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "report_source_enrollment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", name="uq_report_enrollment_company"),
        ForeignKeyConstraint(["tenant_id", "company_id"], ["company.tenant_id", "company.id"]),
        Index("ix_report_enrollment_discovery", "status", "id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
