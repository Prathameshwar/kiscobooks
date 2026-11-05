"""Catalog-owned custom uniqueness and sequence state; no definition authority."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import Quantity, UtcDateTime, Uuid7
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column


class CustomFieldUniqueClaim(IdMixin, TenantMixin, Base):
    __tablename__ = "custom_field_unique_claim"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope_company_id",
            "entity_type",
            "field_key",
            "value_hash",
            name="uq_custom_field_claim_value",
        ),
        Index("ix_custom_field_claim_owner", "tenant_id", "company_id", "entity_type", "entity_id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    scope_company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32).with_variant(mysql.BINARY(32), "mysql"), nullable=False
    )
    canonical_value: Mapped[bytes] = mapped_column(
        LargeBinary(4096).with_variant(mysql.VARBINARY(4096), "mysql"), nullable=False
    )


class CustomFieldSequence(IdMixin, TenantMixin, Base):
    __tablename__ = "custom_field_sequence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "cycle_key",
            name="uq_custom_field_sequence_scope",
        ),
        CheckConstraint("next_value >= 1", name="custom_field_sequence_positive"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    cycle_key: Mapped[str] = mapped_column(String(40), nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CustomFieldValueIndex(IdMixin, TenantMixin, Base):
    __tablename__ = "custom_field_value_index"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "entity_type",
            "entity_id",
            "field_key",
            "generation",
            name="uq_custom_field_index_owner",
        ),
        Index(
            "ix_custom_index_text",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "generation",
            "value_text",
            "entity_id",
        ),
        Index(
            "ix_custom_index_number",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "generation",
            "value_number",
            "entity_id",
        ),
        Index(
            "ix_custom_index_date",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "generation",
            "value_date",
            "entity_id",
        ),
        Index(
            "ix_custom_index_time",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "generation",
            "value_datetime_at",
            "entity_id",
        ),
        Index(
            "ix_custom_index_bool",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "generation",
            "value_bool",
            "entity_id",
        ),
        CheckConstraint("generation >= 1", name="custom_index_generation"),
        CheckConstraint(
            "(value_text IS NOT NULL) + (value_number IS NOT NULL) + (value_date IS NOT NULL) "
            "+ (value_datetime_at IS NOT NULL) + (value_bool IS NOT NULL) = 1",
            name="custom_index_one_value",
        ),
        CheckConstraint(
            "currency IS NULL OR value_number IS NOT NULL", name="custom_index_currency"
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    value_text: Mapped[str | None] = mapped_column(
        String(512).with_variant(mysql.VARCHAR(512, collation="utf8mb4_bin"), "mysql"),
        nullable=True,
    )
    value_number: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    value_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    value_datetime: Mapped[dt.datetime | None] = mapped_column(
        "value_datetime_at", UtcDateTime, nullable=True
    )
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)


class CustomFieldValueMember(IdMixin, TenantMixin, Base):
    __tablename__ = "custom_field_value_member"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "entity_type",
            "entity_id",
            "field_key",
            "generation",
            "member_value",
            name="uq_custom_field_member_owner",
        ),
        Index(
            "ix_custom_member_lookup",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "generation",
            "member_value",
            "entity_id",
        ),
        CheckConstraint("generation >= 1", name="custom_member_generation"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    member_value: Mapped[str] = mapped_column(
        String(200).with_variant(mysql.VARCHAR(200, collation="utf8mb4_bin"), "mysql"),
        nullable=False,
    )
