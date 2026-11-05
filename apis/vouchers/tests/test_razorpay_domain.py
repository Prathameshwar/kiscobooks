"""B42 ingress boundary; successful parsing must not post money."""

import hashlib
import hmac
import json

import pytest
from billing_platform.errors import PermissionDeniedError, ValidationFailedError

from vouchers.domain.razorpay import capture_matches, verify_checkout, verify_webhook


def test_checkout_signature_uses_server_order_id():
    secret = b"test-secret"
    signature = hmac.new(secret, b"order_123|pay_456", hashlib.sha256).hexdigest()
    verify_checkout(
        order_id="order_123", payment_id="pay_456", signature=signature, api_secret=secret
    )
    with pytest.raises(PermissionDeniedError):
        verify_checkout(
            order_id="order_other", payment_id="pay_456", signature=signature, api_secret=secret
        )
    with pytest.raises(ValidationFailedError, match="identity"):
        verify_checkout(
            order_id="order_é", payment_id="pay_456", signature=signature, api_secret=secret
        )


def test_webhook_signs_raw_body_and_returns_evidence_only():
    secret = b"webhook-test-secret"
    body = json.dumps(
        {
            "event": "payment.captured",
            "account_id": "acc_merchant1",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_456",
                        "order_id": "order_123",
                        "status": "captured",
                        "amount": 12345,
                        "currency": "INR",
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    event = verify_webhook(body, signature=signature, delivery_id="evt_123", webhook_secret=secret)
    assert (event.kind, event.status, event.amount_subunits, event.currency) == (
        "payment.captured",
        "captured",
        12345,
        "INR",
    )
    assert event.body_sha256 == hashlib.sha256(body).hexdigest()
    assert capture_matches(
        event,
        account_id="acc_merchant1",
        order_id="order_123",
        amount_subunits=12345,
        currency="INR",
    )
    with pytest.raises(ValidationFailedError, match="retained intent"):
        capture_matches(
            event,
            account_id="acc_merchant1",
            order_id="order_123",
            amount_subunits=12346,
            currency="INR",
        )
    with pytest.raises(ValidationFailedError, match="retained intent"):
        capture_matches(
            event,
            account_id="acc_merchant2",
            order_id="order_123",
            amount_subunits=12345,
            currency="INR",
        )
    with pytest.raises(PermissionDeniedError):
        verify_webhook(
            body + b" ", signature=signature, delivery_id="evt_123", webhook_secret=secret
        )


def test_authorized_snapshot_is_not_promoted_to_capture():
    secret = b"webhook-test-secret"
    body = json.dumps(
        {
            "event": "payment.authorized",
            "account_id": "acc_merchant1",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_1",
                        "order_id": "order_1",
                        "status": "authorized",
                        "amount": 100,
                        "currency": "INR",
                    }
                }
            },
        }
    ).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    event = verify_webhook(body, signature=signature, delivery_id="evt_1", webhook_secret=secret)
    assert event.status == "authorized"
    assert not capture_matches(
        event, account_id="acc_merchant1", order_id="order_1", amount_subunits=100, currency="INR"
    )
    with pytest.raises(ValidationFailedError):
        verify_webhook(body, signature=signature, delivery_id="", webhook_secret=secret)


def test_webhook_rejects_non_ascii_currency_and_control_delivery_id():
    secret = b"webhook-test-secret"
    body = json.dumps(
        {
            "event": "payment.captured",
            "account_id": "acc_merchant1",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_1",
                        "order_id": "order_1",
                        "status": "captured",
                        "amount": 100,
                        "currency": "\u0130NR",
                    }
                }
            },
        }
    ).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    with pytest.raises(ValidationFailedError, match="unsupported"):
        verify_webhook(body, signature=signature, delivery_id="evt_1", webhook_secret=secret)
    with pytest.raises(ValidationFailedError, match="delivery ID"):
        verify_webhook(body, signature=signature, delivery_id="evt_1\n", webhook_secret=secret)


def test_webhook_requires_merchant_account_identity():
    secret = b"webhook-test-secret"
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_1",
                        "order_id": "order_1",
                        "status": "captured",
                        "amount": 100,
                        "currency": "INR",
                    }
                }
            },
        }
    ).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    with pytest.raises(ValidationFailedError, match="webhook"):
        verify_webhook(body, signature=signature, delivery_id="evt_1", webhook_secret=secret)


def test_webhook_rejects_ambiguous_duplicate_json_keys():
    secret = b"webhook-test-secret"
    body = (
        b'{"event":"payment.captured","account_id":"acc_merchant1",'
        b'"account_id":"acc_merchant2","payload":{"payment":{"entity":{'
        b'"id":"pay_1","order_id":"order_1","status":"captured",'
        b'"amount":100,"currency":"INR"}}}}'
    )
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    with pytest.raises(ValidationFailedError, match="webhook"):
        verify_webhook(body, signature=signature, delivery_id="evt_1", webhook_secret=secret)
