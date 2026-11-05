"""Minimal normalized read-only Identity facts, activated per complete company snapshot.

Only the authenticated projection worker writes these tables. Native authoring,
credentials, party masters, physical stock and costs remain with their owners.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv


class SourceProjection(IdMixin, TenantMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CompanyProjection(SourceProjection):
    __tablename__ = "company_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_company_projection_source"
        ),
        CheckConstraint("source_version > 0", name="company_source_version"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    state_code: Mapped[str] = mapped_column(String(6), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reporting_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    fiscal_year_start_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fiscal_year_start_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    amount_precision: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    quantity_precision: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rounding_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    default_tax_system: Mapped[str] = mapped_column(String(20), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    first_posted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class CompanyFeatureProjection(SourceProjection):
    __tablename__ = "company_feature_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_feature_projection_source"
        ),
        CheckConstraint("source_version > 0", name="feature_source_version"),
        Index("ix_feature_projection_lookup_0", "tenant_id", "company_id", "feature_key"),
        MARIADB_TABLE_ARGS,
    )
    source_company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    feature_key: Mapped[str] = mapped_column(String(60), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    locked_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class CompanyCurrencyAllowanceProjection(SourceProjection):
    __tablename__ = "company_currency_allowance_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_currency_allowance_projection_source"
        ),
        Index(
            "ix_currency_allowance_projection_lookup",
            "tenant_id",
            "company_id",
            "currency_code",
            "is_active",
        ),
        MARIADB_TABLE_ARGS,
    )
    source_company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CustomFieldDefinitionProjection(SourceProjection):
    __tablename__ = "custom_field_definition_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_cf_definition_projection_source"
        ),
        CheckConstraint("source_version > 0", name="cf_definition_source_version"),
        Index(
            "ix_cf_definition_projection_lookup_0",
            "tenant_id",
            "company_id",
            "source_company_id",
            "entity_type",
            "definition_key",
        ),
        MARIADB_TABLE_ARGS,
    )
    source_company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    definition_key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    help_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(150), nullable=True)
    data_type: Mapped[str] = mapped_column(String(30), nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    display_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_searchable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_adoption: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_immutable_after_create: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_feature: Mapped[str | None] = mapped_column(String(60), nullable=True)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    option_source_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    depends_on_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    visibility: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sequence_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    default_value: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FieldConfigProjection(SourceProjection):
    __tablename__ = "field_config_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_field_config_projection_source"
        ),
        CheckConstraint("source_version > 0", name="field_config_source_version"),
        Index(
            "ix_field_config_projection_lookup_0",
            "tenant_id",
            "company_id",
            "source_company_id",
            "entity_type",
            "field_key",
        ),
        MARIADB_TABLE_ARGS,
    )
    source_company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    field_source: Mapped[str] = mapped_column(String(10), nullable=False)
    field_key: Mapped[str] = mapped_column(String(120), nullable=False)
    definition_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    is_visible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    display_order: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    display_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    label_override: Mapped[str | None] = mapped_column(String(150), nullable=True)
    help_text_override: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_value: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FieldPolicyProjection(SourceProjection):
    __tablename__ = "field_policy_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_field_policy_projection_source"
        ),
        CheckConstraint("source_version > 0", name="field_policy_source_version"),
        Index(
            "ix_field_policy_projection_lookup_0",
            "tenant_id",
            "company_id",
            "entity_type",
            "subject_type",
            "subject_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    subject_type: Mapped[str] = mapped_column(String(12), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    field_key: Mapped[str] = mapped_column(String(120), nullable=False)
    access: Mapped[str] = mapped_column(String(10), nullable=False)
    effect: Mapped[str] = mapped_column(String(10), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(12), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    predicate_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class RoleAssignmentProjection(SourceProjection):
    __tablename__ = "role_assignment_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_role_assignment_projection_source"
        ),
        CheckConstraint("source_version > 0", name="role_assignment_source_version"),
        Index(
            "ix_role_assignment_projection_lookup_0",
            "tenant_id",
            "company_id",
            "subject_type",
            "subject_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    subject_type: Mapped[str] = mapped_column(String(12), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(12), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class UserGroupMemberProjection(SourceProjection):
    __tablename__ = "user_group_member_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_group_member_projection_source"
        ),
        CheckConstraint("source_version > 0", name="group_member_source_version"),
        Index(
            "ix_group_member_projection_lookup_0",
            "tenant_id",
            "company_id",
            "user_id",
            "user_group_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    user_group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class UserProjection(SourceProjection):
    __tablename__ = "user_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "source_id", name="uq_user_projection_source"),
        CheckConstraint("source_version > 0", name="user_source_version"),
        MARIADB_TABLE_ARGS,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class UserGroupProjection(SourceProjection):
    __tablename__ = "user_group_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "source_id", name="uq_group_projection_source"),
        CheckConstraint("source_version > 0", name="group_source_version"),
        MARIADB_TABLE_ARGS,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class RoleProjection(SourceProjection):
    __tablename__ = "role_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "source_id", name="uq_role_projection_source"),
        CheckConstraint("source_version > 0", name="role_source_version"),
        MARIADB_TABLE_ARGS,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PartyProjection(SourceProjection):
    __tablename__ = "party_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "source_id", name="uq_party_projection_source"),
        CheckConstraint("source_version > 0", name=conv("ck_party_projection_source_version")),
        Index("ix_party_projection_lookup_0", "tenant_id", "company_id", "party_kind", "code"),
        MARIADB_TABLE_ARGS,
    )
    party_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)


class CustomerTypeProjection(SourceProjection):
    __tablename__ = "customer_type_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_customer_type_projection_source"
        ),
        CheckConstraint(
            "source_version > 0", name=conv("ck_customer_type_projection_source_version")
        ),
        Index("ix_customer_type_projection_lookup_0", "tenant_id", "company_id", "code"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CustomerPricingProjection(SourceProjection):
    __tablename__ = "customer_pricing_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_id", name="uq_customer_pricing_projection_source"
        ),
        CheckConstraint(
            "source_version > 0", name=conv("ck_customer_pricing_projection_source_version")
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=conv("ck_customer_pricing_projection_dates"),
        ),
        Index(
            "ix_customer_pricing_projection_lookup_0",
            "tenant_id",
            "company_id",
            "party_id",
            "valid_from",
        ),
        MARIADB_TABLE_ARGS,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    customer_type_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ProjectionCheckpoint(IdMixin, TenantMixin, Base):
    __tablename__ = "projection_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "source_key", name="uq_projection_checkpoint_source"
        ),
        CheckConstraint("source_version >= 0", name="checkpoint_source_version"),
        CheckConstraint(
            "snapshot_source_version IS NULL OR (snapshot_source_version > 0 "
            "AND snapshot_source_version <= source_version)",
            name="checkpoint_snapshot_version",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    snapshot_source_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unavailable")


class SourceEventBuffer(IdMixin, TenantMixin, Base):
    __tablename__ = "source_event_buffer"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_key", "source_version", name="uq_source_buffer_version"
        ),
        UniqueConstraint("tenant_id", "message_id", name="uq_source_buffer_message"),
        CheckConstraint(
            "source_version > 1 AND previous_version = source_version - 1",
            name="buffer_contiguous_version",
        ),
        Index("ix_source_buffer_retention", "tenant_id", "received_at", "id"),
        MARIADB_TABLE_ARGS,
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    previous_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    received_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)


PROJECTION_MODELS: dict[str, type[SourceProjection]] = {
    "company": CompanyProjection,
    "feature": CompanyFeatureProjection,
    "currency_allowance": CompanyCurrencyAllowanceProjection,
    "custom_definition": CustomFieldDefinitionProjection,
    "field_config": FieldConfigProjection,
    "field_policy": FieldPolicyProjection,
    "role_assignment": RoleAssignmentProjection,
    "group_member": UserGroupMemberProjection,
    "user": UserProjection,
    "group": UserGroupProjection,
    "role": RoleProjection,
}
