"""Errors of the local provider. Messages are written for the person; none names an account."""

from __future__ import annotations

from billing_platform.errors import PlatformError


class LocalAuthUnavailableError(PlatformError):
    status_code = 503
    code = "local_auth_unavailable"


class InvalidCredentialsError(PlatformError):
    """Identical for an unknown email and a wrong password."""

    status_code = 401
    code = "invalid_credentials"


class AccountPendingError(PlatformError):
    """Said only to someone who proved the password: the sign-up is still being reviewed."""

    status_code = 403
    code = "account_pending"


class AccountDisabledError(PlatformError):
    status_code = 403
    code = "account_disabled"


class AccountLockedError(PlatformError):
    status_code = 423
    code = "account_locked"

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many failed attempts. Try again later.")
        self.retry_after = retry_after


class AuthorizationRequestInvalidError(PlatformError):
    status_code = 404
    code = "authorization_request_invalid"


class RegistrationUnavailableError(PlatformError):
    """Generic on purpose: it must not say whether the email or username is already used."""

    status_code = 422
    code = "registration_unavailable"


class RecoveryInvalidError(PlatformError):
    status_code = 404
    code = "recovery_invalid"


class OAuthError(Exception):
    """An RFC 6749 error for the token and revocation endpoints (not the platform envelope)."""

    def __init__(self, error: str, description: str, status: int = 400) -> None:
        super().__init__(description)
        self.error, self.description, self.status = error, description, status


class AuthorizeError(Exception):
    """A fault in an authorization request.

    ``redirect_uri`` is set only once the client and redirect URI have been validated: until then
    the error is shown, never redirected to (an unvalidated URI is an open redirect).
    """

    def __init__(
        self,
        error: str,
        description: str,
        *,
        redirect_uri: str | None = None,
        state: str | None = None,
    ) -> None:
        super().__init__(description)
        self.error, self.description = error, description
        self.redirect_uri, self.state = redirect_uri, state


class TooManyAttemptsError(PlatformError):
    status_code = 429
    code = "rate_limited"
