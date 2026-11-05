"""Razorpay ingress validation; verified evidence is not a posting instruction."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.webhooks import verify_sha256_hmac


@dataclass(frozen=True, slots=True)
class PaymentEvent:
    delivery_id: str
    account_id: str
    kind: str
    payment_id: str
    order_id: str
    status: str
    amount_subunits: int
    currency: str
    body_sha256: str


def verify_checkout(*, order_id: str, payment_id: str, signature: str, api_secret: bytes) -> None:
    """Bind the checkout response to the server-retained order, not client order data."""
    if (
        not order_id.startswith("order_")
        or not payment_id.startswith("pay_")
        or len(order_id) > 80
        or len(payment_id) > 80
        or not order_id.isascii()
        or not payment_id.isascii()
    ):
        raise ValidationFailedError("invalid Razorpay checkout identity")
    if not signature or not api_secret:
        raise PermissionDeniedError("invalid Razorpay checkout signature")
    expected = hmac.new(
        api_secret, f"{order_id}|{payment_id}".encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PermissionDeniedError("invalid Razorpay checkout signature")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationFailedError(f"invalid Razorpay {name}")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Razorpay webhook key")
        result[key] = value
    return result


def verify_webhook(
    body: bytes, *, signature: str, delivery_id: str, webhook_secret: bytes
) -> PaymentEvent:
    """Verify exact raw bytes, then extract bounded payment evidence for durable dedupe."""
    if not body or len(body) > 128 * 1024 or not webhook_secret:
        raise ValidationFailedError("invalid Razorpay webhook body or secret")
    if (
        not delivery_id
        or len(delivery_id) > 120
        or not delivery_id.isascii()
        or not delivery_id.isprintable()
        or delivery_id != delivery_id.strip()
    ):
        raise ValidationFailedError("Razorpay delivery ID is required")
    verify_sha256_hmac(body, secret=webhook_secret, signature=signature)
    try:
        payload = _object(json.loads(body, object_pairs_hook=_unique_object), "payload")
        payment = _object(
            _object(_object(payload["payload"], "payload")["payment"], "payment")["entity"],
            "payment entity",
        )
        account_id = payload["account_id"]
        kind = payload["event"]
        payment_id = payment["id"]
        order_id = payment["order_id"]
        status = payment["status"]
        amount = payment["amount"]
        currency = payment["currency"]
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ValidationFailedError("invalid Razorpay payment webhook") from exc
    if (
        not isinstance(account_id, str)
        or not account_id.startswith("acc_")
        or len(account_id) > 80
        or not account_id.isascii()
        or not account_id.removeprefix("acc_").isalnum()
        or kind not in {"payment.authorized", "payment.captured", "payment.failed"}
        or not isinstance(payment_id, str)
        or not payment_id.startswith("pay_")
        or len(payment_id) > 80
        or not payment_id.isascii()
        or not isinstance(order_id, str)
        or not order_id.startswith("order_")
        or len(order_id) > 80
        or not order_id.isascii()
        or status not in {"authorized", "captured", "failed"}
        or type(amount) is not int
        or amount <= 0
        or not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
        or currency != currency.upper()
    ):
        raise ValidationFailedError("unsupported Razorpay payment event")
    return PaymentEvent(
        delivery_id,
        account_id,
        kind,
        payment_id,
        order_id,
        status,
        amount,
        currency,
        hashlib.sha256(body).hexdigest(),
    )


def capture_matches(
    event: PaymentEvent, *, account_id: str, order_id: str, amount_subunits: int, currency: str
) -> bool:
    """Reject mismatched capture evidence; authorized/failed stays non-posting."""
    if (
        event.account_id != account_id
        or event.order_id != order_id
        or event.amount_subunits != amount_subunits
        or event.currency != currency
    ):
        raise ValidationFailedError("Razorpay payment does not match the retained intent")
    return event.kind == "payment.captured" and event.status == "captured"
