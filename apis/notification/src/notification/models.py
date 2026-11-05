"""Notification persistence model; fields mirror docs/notification.md exactly."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import (
    AuditMixin,
    DeactivableMixin,
    IdMixin,
    StatusMixin,
    TenantMixin,
)
from billing_platform.db.platform_models import Outbox, ProcessedMessage
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BINARY, CHAR, MEDIUMBLOB, MEDIUMTEXT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from notification.ownership import SpaceMixin

Binary32 = LargeBinary(32).with_variant(BINARY(32), "mysql")
MediumBinary = LargeBinary().with_variant(MEDIUMBLOB(), "mysql")
MediumText = Text().with_variant(MEDIUMTEXT(), "mysql")


class NotificationSpace(IdMixin, TenantMixin, Base):
    __tablename__ = "notification_space"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", name="uq_notification_space_owner_kind"),
        UniqueConstraint("id", "tenant_id", name="uq_notification_space_id_owner"),
        MARIADB_TABLE_ARGS,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)


class ProviderAccount(SpaceMixin, IdMixin, TenantMixin, StatusMixin, AuditMixin, Base):
    __tablename__ = "provider_account"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_provider_account_tenant_id_key"),
        UniqueConstraint("callback_key", name="uq_provider_account_callback_key"),
        Index("ix_provider_account_tenant_id_channel_status", "tenant_id", "channel", "status"),
        MARIADB_TABLE_ARGS,
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    callback_key: Mapped[str] = mapped_column(
        String(43).with_variant(CHAR(43, charset="ascii", collation="ascii_bin"), "mysql"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(60), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    callback_secret_ref: Mapped[str | None] = mapped_column(String(500))
    region: Mapped[str | None] = mapped_column(String(40))
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class SenderIdentity(SpaceMixin, IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    __tablename__ = "sender_identity"
    __table_args__ = (
        UniqueConstraint("provider_account_id", "key", name="uq_sender_identity_provider_key"),
        UniqueConstraint(
            "provider_account_id", "external_sender_id", name="uq_sender_identity_provider_external"
        ),
        MARIADB_TABLE_ARGS,
    )
    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("provider_account.id"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(30), nullable=False)
    external_sender_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    reply_to_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    verified_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


class RecipientEndpoint(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "recipient_endpoint"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "company_id",
            "channel",
            "destination_hmac",
            name="uq_recipient_endpoint_subject_channel_destination",
        ),
        Index("ix_recipient_endpoint_tenant_subject", "tenant_id", "subject_type", "subject_id"),
        Index(
            "ix_recipient_endpoint_tenant_company_subject",
            "tenant_id",
            "company_id",
            "subject_type",
            "subject_id",
        ),
        Index("ix_recipient_endpoint_tenant_destination", "tenant_id", "destination_hmac"),
        MARIADB_TABLE_ARGS,
    )
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False, default=SCOPE_ALL)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    destination_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    destination_hmac: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    destination_masked: Mapped[str] = mapped_column(String(320), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    health_status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    last_failure_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    deactivated_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


class PartyEndpointCheckpoint(SpaceMixin, IdMixin, TenantMixin, Base):
    """Monotonic owner version, including the no-active-destination tombstone."""

    __tablename__ = "party_endpoint_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "party_id",
            "purpose",
            "channel",
            name="uq_party_endpoint_checkpoint_source",
        ),
        Index("ix_party_endpoint_checkpoint_party", "tenant_id", "company_id", "party_id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)


class VoucherSendState(SpaceMixin, IdMixin, TenantMixin, Base):
    """Latest terminal voucher state for cancelling pending delivery on replay."""

    __tablename__ = "voucher_send_state"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "voucher_id", name="uq_voucher_send_state_source"
        ),
        Index("ix_voucher_send_state_voucher", "tenant_id", "company_id", "voucher_id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class NotificationPreference(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "notification_preference"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "event_key",
            "channel",
            name="uq_notification_preference_subject_event_channel",
        ),
        MARIADB_TABLE_ARGS,
    )
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_updated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    projected_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class ConsentState(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "consent_state"
    __table_args__ = (
        UniqueConstraint(
            "recipient_endpoint_id", "purpose", name="uq_consent_state_endpoint_purpose"
        ),
        Index("ix_consent_state_tenant_state_expires", "tenant_id", "state", "expires_at"),
        MARIADB_TABLE_ARGS,
    )
    recipient_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("recipient_endpoint.id"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    lawful_basis: Mapped[str | None] = mapped_column(String(40))
    evidence_ref: Mapped[str | None] = mapped_column(String(500))
    effective_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    last_event_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class ConsentEvent(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "consent_event"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source", "source_event_key", name="uq_consent_event_source_key"
        ),
        Index(
            "ix_consent_event_endpoint_purpose_time",
            "recipient_endpoint_id",
            "purpose",
            "occurred_at",
        ),
        MARIADB_TABLE_ARGS,
    )
    recipient_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("recipient_endpoint.id"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    evidence_ref: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)


class Suppression(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "suppression"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source", "source_event_key", name="uq_suppression_source_key"
        ),
        Index(
            "ix_suppression_resolution",
            "tenant_id",
            "channel",
            "destination_hmac",
            "valid_from",
            "valid_to",
        ),
        MARIADB_TABLE_ARGS,
    )
    recipient_endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, ForeignKey("recipient_endpoint.id")
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    destination_hmac: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    valid_to: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7)


class NotificationTemplate(SpaceMixin, IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    __tablename__ = "notification_template"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "key", name="uq_notification_template_company_key"
        ),
        Index("ix_notification_template_event", "tenant_id", "company_id", "event_key", "category"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    default_locale: Mapped[str] = mapped_column(String(35), nullable=False)
    variable_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class TemplateVariant(SpaceMixin, IdMixin, TenantMixin, DeactivableMixin, Base):
    __tablename__ = "template_variant"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "channel", "locale", name="uq_template_variant_channel_locale"
        ),
        MARIADB_TABLE_ARGS,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_template.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7)


class TemplateVersion(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "template_version"
    __table_args__ = (
        UniqueConstraint("template_variant_id", "version", name="uq_template_version_number"),
        UniqueConstraint(
            "template_variant_id", "content_sha256", name="uq_template_version_content"
        ),
        MARIADB_TABLE_ARGS,
    )
    template_variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("template_variant.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_text: Mapped[str | None] = mapped_column(String(998))
    body_text: Mapped[str] = mapped_column(MediumText, nullable=False)
    body_html: Mapped[str | None] = mapped_column(MediumText)
    channel_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    content_sha256: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7)


class TemplateActivation(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "template_activation"
    __table_args__ = (
        Index(
            "ix_template_activation_variant_window", "template_variant_id", "valid_from", "valid_to"
        ),
        Index("ix_template_activation_tenant_window", "tenant_id", "valid_from", "valid_to"),
        MARIADB_TABLE_ARGS,
    )
    template_variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("template_variant.id"), nullable=False
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("template_version.id"), nullable=False
    )
    valid_from: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    valid_to: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    activated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    activation_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)


class ProviderTemplateBinding(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "provider_template_binding"
    __table_args__ = (
        UniqueConstraint(
            "provider_account_id", "external_template_id", name="uq_binding_provider_external"
        ),
        UniqueConstraint(
            "template_version_id", "provider_account_id", name="uq_binding_version_provider"
        ),
        MARIADB_TABLE_ARGS,
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("template_version.id"), nullable=False
    )
    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("provider_account.id"), nullable=False
    )
    external_template_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_name: Mapped[str] = mapped_column(String(512), nullable=False)
    external_language: Mapped[str] = mapped_column(String(35), nullable=False)
    external_category: Mapped[str | None] = mapped_column(String(40))
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False)
    quality_status: Mapped[str | None] = mapped_column(String(20))
    rejection_code: Mapped[str | None] = mapped_column(String(120))
    rejection_detail: Mapped[str | None] = mapped_column(String(1000))
    submitted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    synced_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class RoutingRule(SpaceMixin, IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    __tablename__ = "routing_rule"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "event_key",
            "category",
            "channel",
            "priority",
            name="uq_routing_rule_resolution_priority",
        ),
        Index(
            "ix_routing_rule_active_resolution",
            "tenant_id",
            "company_id",
            "event_key",
            "category",
            "channel",
            "is_active",
            "priority",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("provider_account.id"), nullable=False
    )
    sender_identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("sender_identity.id"), nullable=False
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    initial_backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class NotificationRequest(SpaceMixin, IdMixin, TenantMixin, StatusMixin, Base):
    __tablename__ = "notification_request"
    __table_args__ = (
        UniqueConstraint("source_message_id", name="uq_notification_request_source_message"),
        Index("ix_notification_request_status_schedule", "tenant_id", "status", "scheduled_at"),
        Index("ix_notification_request_aggregate", "tenant_id", "aggregate_type", "aggregate_id"),
        Index("ix_notification_request_correlation", "tenant_id", "correlation_id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_service: Mapped[str] = mapped_column(String(40), nullable=False)
    target_tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    source_message_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    trace_id: Mapped[str | None] = mapped_column(
        String(32).with_variant(CHAR(32, charset="ascii", collation="ascii_bin"), "mysql")
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger().with_variant(TINYINT(unsigned=True), "mysql"), nullable=False
    )
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    expires_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    context_ciphertext: Mapped[bytes | None] = mapped_column(MediumBinary)
    context_sha256: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    received_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


class NotificationDelivery(SpaceMixin, IdMixin, TenantMixin, StatusMixin, Base):
    __tablename__ = "notification_delivery"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "recipient_endpoint_id",
            "channel",
            name="uq_notification_delivery_request_endpoint_channel",
        ),
        Index("ix_notification_delivery_status_next", "tenant_id", "status", "next_attempt_at"),
        Index(
            "ix_notification_delivery_provider_message",
            "provider_account_id",
            "provider_message_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_request.id"), nullable=False
    )
    recipient_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("recipient_endpoint.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    destination_hmac: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    destination_masked: Mapped[str] = mapped_column(String(320), nullable=False)
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("template_version.id"), nullable=False
    )
    provider_template_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, ForeignKey("provider_template_binding.id")
    )
    use_case_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey(
            "notification_use_case_binding.id", name="fk_notification_delivery_assignment"
        ),
    )
    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("provider_account.id"), nullable=False
    )
    sender_identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("sender_identity.id"), nullable=False
    )
    routing_rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("routing_rule.id"), nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(String(120))
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    read_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    failed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)


class NotificationContent(SpaceMixin, TenantMixin, Base):
    __tablename__ = "notification_content"
    __table_args__ = (MARIADB_TABLE_ARGS,)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_delivery.id"), primary_key=True
    )
    subject_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    body_text_ciphertext: Mapped[bytes | None] = mapped_column(MediumBinary)
    body_html_ciphertext: Mapped[bytes | None] = mapped_column(MediumBinary)
    payload_ciphertext: Mapped[bytes | None] = mapped_column(MediumBinary)
    content_sha256: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    purged_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


class DeliveryAttempt(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "delivery_attempt"
    __table_args__ = (
        UniqueConstraint("delivery_id", "attempt_number", name="uq_delivery_attempt_number"),
        UniqueConstraint(
            "provider_account_id", "attempt_key", name="uq_delivery_attempt_provider_key"
        ),
        Index("ix_delivery_attempt_provider_message", "provider_account_id", "provider_message_id"),
        MARIADB_TABLE_ARGS,
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_delivery.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("provider_account.id"), nullable=False
    )
    sender_identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("sender_identity.id"), nullable=False
    )
    attempt_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    provider_error_code: Mapped[str | None] = mapped_column(String(120))
    error_class: Mapped[str | None] = mapped_column(String(80))
    retry_after_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    request_sha256: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    response_sha256: Mapped[bytes | None] = mapped_column(Binary32)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)


class ProviderEvent(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "provider_event"
    __table_args__ = (
        UniqueConstraint(
            "provider_account_id", "external_event_key", name="uq_provider_event_external"
        ),
        Index("ix_provider_event_message", "provider_account_id", "provider_message_id"),
        Index("ix_provider_event_processing", "tenant_id", "processing_status", "received_at"),
        MARIADB_TABLE_ARGS,
    )
    provider_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("provider_account.id"), nullable=False
    )
    external_event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_key: Mapped[str | None] = mapped_column(String(80))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provider_occurred_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    received_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    payload_ciphertext: Mapped[bytes | None] = mapped_column(MediumBinary)
    payload_sha256: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, ForeignKey("notification_delivery.id")
    )
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False)
    processed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    processing_error: Mapped[str | None] = mapped_column(String(500))


class DeliveryEvent(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "delivery_event"
    __table_args__ = (
        UniqueConstraint("source", "source_event_key", name="uq_delivery_event_source_key"),
        Index("ix_delivery_event_timeline", "tenant_id", "delivery_id", "observed_at"),
        MARIADB_TABLE_ARGS,
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_delivery.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(120))
    provider_occurred_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    observed_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)


class Attachment(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "attachment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "storage_key", name="uq_attachment_storage_key"),
        Index("ix_attachment_expiry", "tenant_id", "expires_at"),
        Index("ix_attachment_scan", "tenant_id", "scan_status"),
        MARIADB_TABLE_ARGS,
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    purged_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


class DeliveryAttachment(SpaceMixin, TenantMixin, Base):
    __tablename__ = "delivery_attachment"
    __table_args__ = (
        UniqueConstraint("delivery_id", "display_order", name="uq_delivery_attachment_order"),
        MARIADB_TABLE_ARGS,
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_delivery.id"), primary_key=True
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("attachment.id"), primary_key=True
    )
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class ChannelSetting(SpaceMixin, IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "channel_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="uq_channel_setting_channel"),
        MARIADB_TABLE_ARGS,
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UseCaseBinding(SpaceMixin, IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "notification_use_case_binding"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "event_key",
            "trigger_key",
            "channel",
            "valid_from",
            name="uq_notification_use_case_binding_start",
        ),
        Index(
            "ix_notification_use_case_binding_resolve",
            "tenant_id",
            "space_id",
            "company_id",
            "event_key",
            "channel",
            "valid_from",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_template.id"), nullable=False
    )
    valid_from: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    valid_to: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


class NotificationJob(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "notification_job"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_key", name="uq_notification_job_request"),
        Index("ix_notification_job_due", "status", "created_at"),
        MARIADB_TABLE_ARGS,
    )
    request_key: Mapped[bytes] = mapped_column(Binary32, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    result_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    request_hash: Mapped[bytes | None] = mapped_column(Binary32)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reason_code: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)


class PlanningOutcome(SpaceMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "notification_planning_outcome"
    __table_args__ = (
        UniqueConstraint("request_id", "channel", name="uq_notification_planning_outcome_channel"),
        MARIADB_TABLE_ARGS,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("notification_request.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, nullable=False)


# Every notification-owned reference carries the same tenant/space at the DB boundary.
# Keep the original single-column FK for backward-compatible migration rollout.
_SPACE_TABLES = [
    table
    for mapper in Base.registry.mappers
    if isinstance(table := mapper.local_table, Table) and issubclass(mapper.class_, SpaceMixin)
]
for _table in _SPACE_TABLES:
    for _unique in list(_table.constraints):
        if isinstance(_unique, UniqueConstraint) and "tenant_id" in _unique.columns:
            _columns = [c.name for c in _unique.columns]
            _columns.insert(_columns.index("tenant_id") + 1, "space_id")
            _table.constraints.remove(_unique)
            _table.append_constraint(UniqueConstraint(*_columns, name=_unique.name))
    _pk = [column.name for column in _table.primary_key.columns]
    _table.append_constraint(
        UniqueConstraint(*_pk, "tenant_id", "space_id", name=f"uq_{_table.name}_space_owner")
    )
for _table in _SPACE_TABLES:
    for _fk in list(_table.foreign_keys):
        if _fk.column.table not in _SPACE_TABLES:
            continue
        _table.append_constraint(
            ForeignKeyConstraint(
                [_fk.parent.name, "tenant_id", "space_id"],
                [
                    f"{_fk.column.table.name}.{c}"
                    for c in (_fk.column.name, "tenant_id", "space_id")
                ],
                name=f"fk_{_table.name}_{_fk.parent.name}_space",
                ondelete="RESTRICT",
            )
        )


# Leading ownership and stable keyset columns match the public list/query contracts.
Index(
    "ix_delivery_attempt_capacity",
    DeliveryAttempt.tenant_id,
    DeliveryAttempt.space_id,
    DeliveryAttempt.started_at,
    DeliveryAttempt.provider_account_id,
)
_LIST_INDEXES: dict[str, list[tuple[str, ...]]] = {
    "provider_account": [("updated_at", "id"), ("display_name", "id")],
    "notification_request": [
        ("received_at", "id"),
        ("status", "received_at", "id"),
        ("event_key", "received_at", "id"),
        ("company_id", "aggregate_id", "received_at", "id"),
    ],
    "notification_delivery": [
        ("created_at", "id"),
        ("status", "created_at", "id"),
        ("channel", "created_at", "id"),
        ("request_id", "created_at", "id"),
    ],
    "notification_template": [
        ("created_at", "id"),
        ("key", "id"),
        ("event_key", "company_id", "is_active"),
    ],
    "routing_rule": [
        ("created_at", "id"),
        ("priority", "id"),
        ("channel", "company_id", "event_key", "category"),
    ],
    "sender_identity": [("provider_account_id", "id")],
    "template_variant": [("template_id", "id")],
    "template_version": [("template_variant_id", "id")],
    "template_activation": [("template_variant_id", "id")],
    "provider_template_binding": [("template_version_id", "id")],
    "delivery_attempt": [("delivery_id", "id")],
    "delivery_event": [("delivery_id", "id")],
    "suppression": [("valid_from", "id")],
    "recipient_endpoint": [("subject_id", "id")],
    "provider_event": [
        ("received_at", "id"),
        ("processing_status", "received_at", "id"),
        ("provider_account_id", "received_at", "id"),
    ],
}
for _name, _shapes in _LIST_INDEXES.items():
    _list_table = Base.metadata.tables[_name]
    for _number, _shape in enumerate(_shapes, 1):
        Index(
            f"ix_{_name}_scoped_list_{_number}",
            *(_list_table.c[c] for c in ("tenant_id", "space_id", *_shape)),
        )


__all__ = [
    "Attachment",
    "ConsentEvent",
    "ConsentState",
    "DeliveryAttachment",
    "DeliveryAttempt",
    "DeliveryEvent",
    "NotificationContent",
    "NotificationDelivery",
    "NotificationPreference",
    "NotificationRequest",
    "NotificationTemplate",
    "Outbox",
    "PartyEndpointCheckpoint",
    "ProcessedMessage",
    "ProviderAccount",
    "ProviderEvent",
    "ProviderTemplateBinding",
    "RecipientEndpoint",
    "RoutingRule",
    "SenderIdentity",
    "Suppression",
    "TemplateActivation",
    "TemplateVariant",
    "TemplateVersion",
    "VoucherSendState",
]
