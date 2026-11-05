from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from notification.api.schemas import DeliveryItem, PageMeta, RequestItem, StrictModel
from notification.api.schemas_mgmt import RoutingRuleItem

type Channel = Literal["email", "sms", "whatsapp", "push"]


class Page[T](StrictModel):
    items: list[T]
    page: PageMeta


class ChannelPolicy(StrictModel):
    is_enabled: bool


class ChannelReadiness(StrictModel):
    channel: Channel
    is_enabled: bool
    ready: bool
    reasons: list[str]


class SenderUpdate(StrictModel):
    expected_updated_at: AwareDatetime | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    is_active: bool | None = None


class VariantUpdate(StrictModel):
    is_active: bool


class TemplateUpdate(StrictModel):
    expected_updated_at: AwareDatetime | None = None
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class TemplateDetail(StrictModel):
    id: uuid.UUID
    company_id: uuid.UUID
    key: str
    event_key: str
    category: str
    description: str | None
    default_locale: str
    variable_schema: dict[str, Any]
    is_active: bool
    updated_at: dt.datetime


class VersionDetail(StrictModel):
    id: uuid.UUID
    template_variant_id: uuid.UUID
    version: int
    subject_text: str | None
    body_text: str
    body_html: str | None
    channel_payload: dict[str, Any] | None
    created_at: dt.datetime


class PreviewRequest(StrictModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class PreviewResponse(StrictModel):
    subject: str | None
    body: str
    body_html: str | None


class AssignmentCreate(StrictModel):
    company_id: uuid.UUID
    event_key: str = Field(max_length=120)
    trigger_key: str = Field(max_length=120)
    channel: Channel
    template_id: uuid.UUID
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def window(self) -> AssignmentCreate:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must follow valid_from")
        return self


class AssignmentItem(AssignmentCreate):
    id: uuid.UUID


class EndWindow(StrictModel):
    valid_to: AwareDatetime


class JobItem(StrictModel):
    id: uuid.UUID
    kind: str
    target_id: uuid.UUID
    status: str
    reason_code: str | None
    created_at: dt.datetime
    completed_at: dt.datetime | None


class RouteUpdate(StrictModel):
    expected_updated_at: AwareDatetime | None = None
    is_active: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=32767)
    weight: int | None = Field(default=None, ge=1, le=32767)
    max_attempts: int | None = Field(default=None, ge=1, le=100)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    initial_backoff_seconds: int | None = Field(default=None, ge=1, le=86400)
    max_backoff_seconds: int | None = Field(default=None, ge=1, le=604800)


class RouteDetail(RoutingRuleItem):
    max_attempts: int
    timeout_seconds: int
    initial_backoff_seconds: int
    max_backoff_seconds: int


class DeliveryDetail(DeliveryItem):
    recipient_endpoint_id: uuid.UUID
    provider_message_id: str | None
    template_version_id: uuid.UUID
    use_case_binding_id: uuid.UUID | None
    provider_account_id: uuid.UUID
    sender_identity_id: uuid.UUID
    routing_rule_id: uuid.UUID
    provider_template_binding_id: uuid.UUID | None
    accepted_at: dt.datetime | None
    delivered_at: dt.datetime | None
    completed_at: dt.datetime | None


class RequestDetail(RequestItem):
    source_service: str
    source_event_key: str
    expires_at: dt.datetime | None
    completed_at: dt.datetime | None


class PlanningItem(StrictModel):
    id: uuid.UUID
    request_id: uuid.UUID
    channel: str
    decision: str
    reason_code: str
    created_at: dt.datetime


class AttemptItem(StrictModel):
    id: uuid.UUID
    delivery_id: uuid.UUID
    attempt_number: int
    outcome: str
    http_status: int | None
    provider_error_code: str | None
    started_at: dt.datetime
    completed_at: dt.datetime | None


class EventItem(StrictModel):
    id: uuid.UUID
    delivery_id: uuid.UUID
    source: str
    from_status: str | None
    to_status: str
    reason_code: str | None
    observed_at: dt.datetime


class ProviderReceiptItem(StrictModel):
    id: uuid.UUID
    provider_account_id: uuid.UUID
    provider_message_id: str | None
    attempt_key: str | None
    event_type: str
    processing_status: str
    signature_verified: bool
    received_at: dt.datetime
    processed_at: dt.datetime | None
    delivery_id: uuid.UUID | None


class EffectivePolicy(StrictModel):
    company_id: uuid.UUID
    event_key: str
    trigger_key: str
    channel: Channel
    locale: str | None = Field(default=None, max_length=35)


class EffectiveResult(StrictModel):
    ready: bool
    reasons: list[str]
    template_version_id: uuid.UUID | None = None
    route_id: uuid.UUID | None = None


class ReceiptReconciliation(StrictModel):
    provider_event_id: uuid.UUID


class CallbackConfiguration(StrictModel):
    url: str | None
    signature_scheme: str
    ready: bool


class UseCaseItem(StrictModel):
    key: str
    owner: Literal["platform", "tenant"]
    source: str
    category: str
    triggers: list[str]
    channels: list[Channel]
    required_variables: list[str]
