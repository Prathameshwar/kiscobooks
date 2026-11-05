"""Service-owned metadata view, excluding platform tables this service does not use."""

from __future__ import annotations

from billing_platform.db.base import NAMING_CONVENTION, Base
from sqlalchemy import MetaData

from notification import models  # noqa: F401

TABLES = frozenset(
    {
        "channel_setting",
        "notification_use_case_binding",
        "notification_job",
        "notification_planning_outcome",
        "notification_space",
        "outbox",
        "processed_message",
        "provider_account",
        "sender_identity",
        "recipient_endpoint",
        "party_endpoint_checkpoint",
        "voucher_send_state",
        "notification_preference",
        "consent_state",
        "consent_event",
        "suppression",
        "notification_template",
        "template_variant",
        "template_version",
        "template_activation",
        "provider_template_binding",
        "routing_rule",
        "notification_request",
        "notification_delivery",
        "notification_content",
        "delivery_attempt",
        "provider_event",
        "delivery_event",
        "attachment",
        "delivery_attachment",
    }
)


def service_metadata() -> MetaData:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    for name in TABLES:
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata
