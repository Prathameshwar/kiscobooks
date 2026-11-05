"""Error envelope.

The single assertion that matters here: a response body carries the envelope and
nothing else — no stack trace, no SQL, no internal identifier (CLAUDE.md §5.8).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from billing_platform.errors import (
    ConflictError,
    ErrorEnvelope,
    FeatureNotEnabledError,
    IdempotencyConflictError,
    ImmutableFieldError,
    NotFoundError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (NotFoundError("gone"), 404, "not_found"),
        (PermissionDeniedError("no"), 403, "permission_denied"),
        (FeatureNotEnabledError("off"), 409, "feature_not_enabled"),
        (ValidationFailedError("bad"), 422, "validation_failed"),
        (ConflictError("clash"), 409, "conflict"),
        (ImmutableFieldError("frozen"), 422, "immutable_field"),
        (IdempotencyConflictError("reused"), 422, "idempotency_key_reused"),
    ],
)
def test_status_and_code_per_error(error: PlatformError, status: int, code: str) -> None:
    assert error.status_code == status
    assert error.code == code


def test_feature_gating_is_409_not_403() -> None:
    """403 means *you* may not; 409 means *nobody here* can, yet.

    Collapsing them floods permission-denial audit signal with ordinary
    feature-gated client calls.
    """
    assert PermissionDeniedError("x").status_code == 403
    assert FeatureNotEnabledError("x").status_code == 409


def test_immutable_field_is_422_because_no_role_can_lift_it() -> None:
    assert ImmutableFieldError("currency").status_code == 422


def test_envelope_contains_only_the_error_body() -> None:
    envelope = NotFoundError("company not found").envelope(trace_id="abc123")
    dumped = envelope.model_dump(exclude_none=True)

    assert set(dumped) == {"error"}
    assert dumped["error"] == {
        "code": "not_found",
        "message": "company not found",
        "trace_id": "abc123",
    }


def test_validation_error_carries_field_detail() -> None:
    error = ValidationFailedError("bad input", fields={"legal_name": "required"})
    body = error.envelope().error
    assert body.fields == {"legal_name": "required"}


def test_feature_error_names_the_feature_so_the_client_can_offer_it() -> None:
    error = FeatureNotEnabledError("multi-currency is off", feature="multi_currency")
    assert error.envelope().error.feature == "multi_currency"


def test_envelope_forbids_extra_keys() -> None:
    """extra="forbid" everywhere, so a stray internal field cannot leak."""
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"error": {"code": "x", "message": "y"}, "sql": "SELECT 1"})
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"error": {"code": "x", "message": "y", "traceback": "..."}})


def test_message_is_preserved_as_the_exception_string() -> None:
    assert str(NotFoundError("gone")) == "gone"
