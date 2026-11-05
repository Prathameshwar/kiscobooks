"""Request/response schemas for the management surface (Phases 4-6).

Distinct create/item shapes, ``extra='forbid'``. Immutable evidence (template versions,
consent events) is created, never updated. Secrets and destinations are never accepted or
returned in the clear beyond a mask.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from notification.api.schemas import PageMeta, StrictModel

# --- sender identity ----------------------------------------------------------


class SenderIdentityCreate(StrictModel):
    provider_account_id: uuid.UUID
    key: str = Field(min_length=1, max_length=80)
    sender_type: str = Field(min_length=1, max_length=30)
    external_sender_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=150)
    capabilities: dict[str, Any] | None = None


class SenderIdentityItem(StrictModel):
    updated_at: dt.datetime
    id: uuid.UUID
    provider_account_id: uuid.UUID
    key: str
    sender_type: str
    external_sender_id: str
    display_name: str
    verification_status: str
    is_active: bool


# --- routing rule -------------------------------------------------------------


class RoutingRuleCreate(StrictModel):
    company_id: uuid.UUID
    event_key: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=30)
    channel: str
    provider_account_id: uuid.UUID
    sender_identity_id: uuid.UUID
    priority: int = Field(ge=0, le=32767)
    weight: int = Field(ge=1, le=32767)
    max_attempts: int = Field(ge=1, le=100)
    timeout_seconds: int = Field(ge=1, le=3600)
    initial_backoff_seconds: int = Field(ge=1, le=86400)
    max_backoff_seconds: int = Field(ge=1, le=604800)
    conditions: dict[str, Any] | None = None

    @model_validator(mode="after")
    def backoff_bounds(self) -> RoutingRuleCreate:
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= initial_backoff_seconds")
        return self


class RoutingRuleItem(StrictModel):
    updated_at: dt.datetime
    id: uuid.UUID
    company_id: uuid.UUID
    event_key: str
    category: str
    channel: str
    provider_account_id: uuid.UUID
    sender_identity_id: uuid.UUID
    priority: int
    weight: int
    is_active: bool


class RoutingRulePage(StrictModel):
    items: list[RoutingRuleItem]
    page: PageMeta


# --- suppression --------------------------------------------------------------


class SuppressionCreate(StrictModel):
    channel: str
    #: Raw destination (e.g. email/phone); the HMAC is computed server-side and the raw
    #: value is not stored.
    destination: str = Field(min_length=1, max_length=320)
    scope_type: str  # global | event | category
    scope_key: str = Field(default="", max_length=120)
    reason: str = Field(min_length=1, max_length=40)
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def suppression_window(self) -> SuppressionCreate:
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must follow valid_from")
        if self.scope_type == "global" and self.scope_key:
            raise ValueError("global suppression must not have a scope key")
        if self.scope_type in {"event", "category"} and not self.scope_key.strip():
            raise ValueError("scoped suppression requires a scope key")
        return self


class SuppressionItem(StrictModel):
    id: uuid.UUID
    channel: str
    scope_type: str
    scope_key: str
    reason: str
    source: str
    valid_from: dt.datetime
    valid_to: dt.datetime | None


class SuppressionPage(StrictModel):
    items: list[SuppressionItem]
    page: PageMeta


# --- consent ------------------------------------------------------------------


class ConsentRecord(StrictModel):
    recipient_endpoint_id: uuid.UUID
    purpose: str = Field(min_length=1, max_length=30)
    state: Literal["granted", "denied", "withdrawn", "unknown"]
    lawful_basis: str | None = Field(default=None, max_length=40)
    evidence_ref: str | None = Field(default=None, max_length=500)
    source: str = Field(min_length=1, max_length=40)
    source_event_key: str = Field(min_length=1, max_length=255)
    occurred_at: AwareDatetime
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def consent_window(self) -> ConsentRecord:
        if self.expires_at is not None and self.expires_at <= self.occurred_at:
            raise ValueError("expires_at must follow occurred_at")
        return self


class ConsentStateItem(StrictModel):
    id: uuid.UUID
    recipient_endpoint_id: uuid.UUID
    purpose: str
    state: str
    effective_at: dt.datetime
    expires_at: dt.datetime | None


# --- templates ----------------------------------------------------------------


class TemplateCreate(StrictModel):
    company_id: uuid.UUID
    key: str = Field(min_length=1, max_length=80)
    event_key: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=30)
    description: str | None = Field(default=None, max_length=500)
    default_locale: str = Field(min_length=2, max_length=35)
    variable_schema: dict[str, Any] = Field(default_factory=dict)


class TemplateItem(StrictModel):
    updated_at: dt.datetime
    id: uuid.UUID
    company_id: uuid.UUID
    key: str
    event_key: str
    category: str
    default_locale: str
    is_active: bool


class TemplatePage(StrictModel):
    items: list[TemplateItem]
    page: PageMeta


class VariantCreate(StrictModel):
    channel: str
    locale: str = Field(min_length=2, max_length=35)


class VariantItem(StrictModel):
    id: uuid.UUID
    template_id: uuid.UUID
    channel: str
    locale: str
    is_active: bool


class VersionCreate(StrictModel):
    subject_text: str | None = Field(default=None, max_length=998)
    body_text: str = Field(min_length=1)
    body_html: str | None = None
    channel_payload: dict[str, Any] | None = None


class VersionItem(StrictModel):
    id: uuid.UUID
    template_variant_id: uuid.UUID
    version: int
    subject_text: str | None
    created_at: dt.datetime


class ActivationCreate(StrictModel):
    template_version_id: uuid.UUID
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    activation_reason: str | None = Field(default=None, max_length=500)


class ActivationItem(StrictModel):
    id: uuid.UUID
    template_variant_id: uuid.UUID
    template_version_id: uuid.UUID
    valid_from: dt.datetime
    valid_to: dt.datetime | None


class BindingCreate(StrictModel):
    template_version_id: uuid.UUID
    provider_account_id: uuid.UUID
    external_template_id: str = Field(min_length=1, max_length=255)
    external_name: str = Field(min_length=1, max_length=512)
    external_language: str = Field(min_length=2, max_length=35)
    external_category: str | None = Field(default=None, max_length=40)


class BindingApproval(StrictModel):
    approval_status: str  # pending | approved | rejected
    quality_status: str | None = Field(default=None, max_length=20)
    rejection_code: str | None = Field(default=None, max_length=120)
    rejection_detail: str | None = Field(default=None, max_length=1000)


class BindingItem(StrictModel):
    id: uuid.UUID
    template_version_id: uuid.UUID
    provider_account_id: uuid.UUID
    external_template_id: str
    approval_status: str


# --- attachments --------------------------------------------------------------


class AttachmentCreate(StrictModel):
    storage_key: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(ge=0)
    sha256_hex: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")


class AttachmentItem(StrictModel):
    id: uuid.UUID
    storage_key: str
    media_type: str
    byte_size: int
    scan_status: str
    expires_at: dt.datetime


class ScanStatusUpdate(StrictModel):
    scan_status: str  # pending | clean | infected | error


class DeliveryAttachmentCreate(StrictModel):
    attachment_id: uuid.UUID
    disposition: str = Field(default="attachment", max_length=20)
    content_id: str | None = Field(default=None, max_length=255)
    display_order: int = Field(default=0, ge=0, le=32767)


class DeliveryAttachmentItem(StrictModel):
    delivery_id: uuid.UUID
    attachment_id: uuid.UUID
    disposition: str
    display_order: int


# --- recipient (read only) ----------------------------------------------------


class RecipientEndpointItem(StrictModel):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    company_id: uuid.UUID
    channel: str
    destination_masked: str
    verification_status: str
    health_status: str
    is_active: bool
