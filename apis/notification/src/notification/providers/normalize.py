"""Provider callback event → normalized delivery status (docs/notification.md §2.2).

Each provider names its callback events differently; this maps the captured
``provider_event.event_type`` to a delivery state the state machine understands, per
channel. A ``None`` result means the event is not a state transition (a plain "sent"
acknowledgement, an open/click beacon we do not model as a state) and is marked
processed without advancing the delivery. Pure — the normalizer supplies the strings.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from urllib.parse import parse_qsl

# (channel, lowercased provider event type) -> (delivery status, reason code | None).
# Only genuine state transitions appear; anything absent is a non-advancing event.
_STATUS_MAP: Final[dict[str, dict[str, tuple[str, str | None]]]] = {
    "email": {
        "send": ("accepted", None),
        "delivery": ("delivered", None),
        "open": ("read", None),
        "bounce": ("failed", "bounce"),
        "hard_bounce": ("failed", "hard_bounce"),
        "complaint": ("failed", "complaint"),
        "reject": ("failed", "reject"),
    },
    "sms": {
        "queued": ("accepted", None),
        "sent": ("accepted", None),
        "delivered": ("delivered", None),
        "undelivered": ("failed", "undelivered"),
        "failed": ("failed", "failed"),
    },
    "whatsapp": {
        "sent": ("accepted", None),
        "delivered": ("delivered", None),
        "read": ("read", None),
        "failed": ("failed", "failed"),
    },
    "push": {
        "delivered": ("delivered", None),
        "failed": ("failed", "failed"),
    },
}


def normalized_status(channel: str, event_type: str) -> tuple[str, str | None] | None:
    """The (delivery status, reason) for a callback event, or ``None`` if it is not a
    state transition for this channel."""
    return _STATUS_MAP.get(channel, {}).get(event_type.strip().lower())


@dataclass(frozen=True, slots=True)
class CallbackFact:
    message_id: str | None
    event_type: str
    event_key: str
    occurred_at: datetime | None = None
    attempt_key: str | None = None


def valid_attempt_key(value: object) -> str | None:
    return (
        value
        if isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}:[1-9][0-9]{0,5}", value)
        else None
    )


def _email_attempt(body: bytes) -> str | None:
    try:
        data = json.loads(body)
        if isinstance(data, dict) and data.get("Type") == "Notification":
            data = json.loads(data.get("Message", "{}"))
        mail = data.get("mail") if isinstance(data, dict) else None
        tags = mail.get("tags") if isinstance(mail, dict) else None
        keys = tags.get("attempt_key") if isinstance(tags, dict) else None
        if isinstance(keys, list) and len(keys) == 1 and isinstance(keys[0], str):
            return valid_attempt_key(keys[0].replace("_", ":"))
        return None
    except (ValueError, TypeError):
        return None


def extract_callback_facts(channel: str, body: bytes) -> list[CallbackFact]:
    """Read every status from the verified body, with constituent replay identities."""
    if channel != "whatsapp":
        message_id, event_type, key = extract_callback_metadata(channel, body)
        return (
            [
                CallbackFact(
                    message_id,
                    event_type or "unknown",
                    key,
                    attempt_key=_email_attempt(body) if channel == "email" else None,
                )
            ]
            if key
            else []
        )
    try:
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("entry"), list):
            return []
        facts = []
        for entry in data["entry"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("changes"), list):
                continue
            for change in entry["changes"]:
                value = change.get("value") if isinstance(change, dict) else None
                statuses = value.get("statuses") if isinstance(value, dict) else None
                if not isinstance(statuses, list):
                    continue
                for status in statuses:
                    if not isinstance(status, dict):
                        continue
                    message_id, event_type = status.get("id"), status.get("status")
                    if not isinstance(message_id, str) or not isinstance(event_type, str):
                        continue
                    if not 1 <= len(message_id) <= 255 or not 1 <= len(event_type) <= 80:
                        continue
                    canonical = json.dumps(status, sort_keys=True, separators=(",", ":")).encode()
                    occurred_at = None
                    try:
                        occurred_at = datetime.fromtimestamp(int(status["timestamp"]), UTC)
                    except (KeyError, TypeError, ValueError, OverflowError, OSError):
                        pass
                    facts.append(
                        CallbackFact(
                            message_id,
                            event_type,
                            hashlib.sha256(canonical).hexdigest(),
                            occurred_at,
                            valid_attempt_key(status.get("biz_opaque_callback_data")),
                        )
                    )
        return facts
    except (ValueError, UnicodeDecodeError):
        return []


def extract_callback_metadata(
    channel: str, body: bytes
) -> tuple[str | None, str | None, str | None]:
    """Extract (provider_message_id, event_type, external_event_id) from raw webhook body.

    Handles standard webhook payload formats for Twilio SMS (form urlencoded),
    Meta WhatsApp (JSON), and AWS SES/SNS (JSON).
    """
    if channel == "whatsapp":
        facts = extract_callback_facts(channel, body)
        if facts:
            return facts[0].message_id, facts[0].event_type, hashlib.sha256(body).hexdigest()
        return None, None, None
    if channel == "sms":
        try:
            text = body.decode("utf-8")
            params = dict(parse_qsl(text, keep_blank_values=True))
            if "MessageSid" in params:
                sid = params["MessageSid"]
                status = params.get("MessageStatus")
                if not 1 <= len(sid) <= 255 or (status is not None and len(status) > 80):
                    return None, None, None
                return sid, status, hashlib.sha256(body).hexdigest()
        except (ValueError, KeyError, UnicodeDecodeError):
            return None, None, None

    try:
        data = json.loads(body)
        if isinstance(data, dict):
            if channel == "email":
                if data.get("Type") == "Notification" and "Message" in data:
                    inner_str = data.get("Message", "")
                    if isinstance(inner_str, str) and inner_str.strip().startswith("{"):
                        data = json.loads(inner_str)
                if not isinstance(data, dict):
                    return None, None, None
                event_type = data.get("eventType") or data.get("notificationType")
                bounce = data.get("bounce")
                if (
                    str(event_type).lower() == "bounce"
                    and isinstance(bounce, dict)
                    and bounce.get("bounceType") == "Permanent"
                ):
                    event_type = "hard_bounce"
                mail = data.get("mail", {})
                if not isinstance(mail, dict) or not isinstance(event_type, str):
                    return None, None, None
                message_id = mail.get("messageId")
                if (
                    not isinstance(message_id, str)
                    or not 1 <= len(message_id) <= 255
                    or len(event_type) > 80
                ):
                    return None, None, None
                return (
                    message_id,
                    event_type.lower() if event_type else None,
                    hashlib.sha256(body).hexdigest(),
                )

            if channel in {"sms", "push"}:
                msg_id = data.get("sid") or data.get("message_id") or data.get("name")
                event = data.get("status") or data.get("event_type")
                return (
                    str(msg_id) if msg_id else None,
                    str(event).lower() if event else None,
                    hashlib.sha256(body).hexdigest(),
                )
    except (ValueError, KeyError, json.JSONDecodeError):
        return None, None, None

    return None, None, None
