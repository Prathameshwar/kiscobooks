"""Reviewed product contracts and a tenant-wide serialization point for unique claims."""

import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import JSON, BigInteger, CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CustomFieldAdoption(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "custom_field_adoption"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "entity_type", name="uq_custom_adoption_scope"),
        CheckConstraint("row_version >= 1", name="custom_adoption_version"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    definitions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
