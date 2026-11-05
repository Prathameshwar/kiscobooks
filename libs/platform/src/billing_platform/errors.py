"""The error envelope. Responses carry this and nothing else.

No stack traces, no SQL, no internal identifiers (CLAUDE.md §5.8). Anything a
handler wants to say to an operator goes to the log with the ``trace_id``, not
to the client.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    #: Field-level detail for 422. Maps field path -> reason.
    fields: dict[str, str] | None = None
    #: Set for 409 feature gating so the client can offer to enable it.
    feature: str | None = None
    #: Correlates the response with the log line and the audit event.
    trace_id: str | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class PlatformError(Exception):
    """Base for errors that map to an envelope."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra

    def envelope(self, trace_id: str | None = None) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorBody(
                code=self.code,
                message=self.message,
                trace_id=trace_id,
                **self.extra,
            )
        )


class NotFoundError(PlatformError):
    status_code = 404
    code = "not_found"


class AuthenticationRequiredError(PlatformError):
    """401 — *who are you.* The request carried no usable identity: a missing,
    malformed, or expired signed actor context.

    Distinct from ``PermissionDeniedError`` (403), which is *authenticated but not
    permitted*. Keeping them apart matters: a 401 tells the client to re-authenticate,
    a 403 tells it the identity is fine but the authority is not, and conflating them
    sends a permitted user to a login loop and an unauthenticated one hunting for a
    permission they could never have used.
    """

    status_code = 401
    code = "authentication_required"


class PermissionDeniedError(PlatformError):
    """403 — *you* may not. Distinct from FeatureNotEnabledError on purpose."""

    status_code = 403
    code = "permission_denied"


class FeatureNotEnabledError(PlatformError):
    """409 — *nobody here* can, yet.

    Kept distinct from 403 so permission-denial audit signal, which is worth
    investigating, is not flooded by ordinary feature-gated client calls
    (docs/company-features.md §5).
    """

    status_code = 409
    code = "feature_not_enabled"


class ValidationFailedError(PlatformError):
    status_code = 422
    code = "validation_failed"


class ConflictError(PlatformError):
    status_code = 409
    code = "conflict"


class ImmutableFieldError(PlatformError):
    """A field frozen by domain rule, not by permission.

    422 rather than 403: no actor and no role can lift it, so it is not an
    authorization outcome (docs/company.md §5.2).
    """

    status_code = 422
    code = "immutable_field"


class IdempotencyConflictError(PlatformError):
    """Same idempotency key, different request body.

    A client bug, and it must not silently replay the first response — a mobile
    client that mutated its payload between retries would get the wrong answer
    and never know (docs/identity-db-plan.md, ``idempotency_key.request_hash``).
    """

    status_code = 422
    code = "idempotency_key_reused"
