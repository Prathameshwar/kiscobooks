"""Provider-owned, one-use password recovery. No token is persisted by Identity."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError
from billing_platform.provider_http import ProviderHttpError, provider_json

from identity.config import Settings


class AdministratorRecoveryUnavailableError(PlatformError):
    status_code = 503
    code = "administrator_recovery_unavailable"


class AdministratorRecoveryProvider:
    """A separate credential with object view/reset authority, never change-user authority."""

    @staticmethod
    def subject_field(subject: str | uuid.UUID) -> str | None:
        """OIDC subjects are opaque UIDs; retain legacy UUID links without rewriting them."""
        if re.fullmatch(r"[0-9a-f]{64}", str(subject)):
            return "uid"
        try:
            return "uuid" if str(uuid.UUID(str(subject))) == str(subject) else None
        except ValueError:
            return None

    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.http = http
        base = urlsplit(settings.authentik_recovery_url or "")
        if (
            base.scheme != "https"
            or not base.hostname
            or base.username
            or base.password
            or base.query
            or base.fragment
            or base.path not in ("", "/")
            or not settings.authentik_recovery_token
        ):
            raise AdministratorRecoveryUnavailableError(
                "Password recovery needs configuration. Contact your platform administrator."
            )
        self.base = (settings.authentik_recovery_url or "").rstrip("/")
        self.headers = {
            "Authorization": "Bearer " + settings.authentik_recovery_token.get_secret_value()
        }
        self.email_stage = settings.authentik_recovery_email_stage

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, str] | None = None,
        *,
        no_content: bool = False,
    ) -> dict[str, Any]:
        # Never expose provider bodies, credentials, URLs or tokens in an error.
        try:
            return await provider_json(
                self.http,
                method,
                self.base + path,
                headers=self.headers,
                body=body,
                max_bytes=65536,
                expected_status=204 if no_content else 200,
            )
        except ProviderHttpError:
            raise AdministratorRecoveryUnavailableError(
                "Recovery could not be confirmed. "
                "Check the sign-in provider before creating another link."
            ) from None

    async def recover(
        self, subject: str | uuid.UUID, delivery: Literal["link", "email"], expected_email: str
    ) -> tuple[str | None, dt.datetime]:
        if delivery == "email" and not self.email_stage:
            raise AdministratorRecoveryUnavailableError(
                "Recovery email needs a configured SMTP email stage. "
                "Create a recovery link instead."
            )
        field = self.subject_field(subject)
        if field is None:
            raise AdministratorRecoveryUnavailableError(
                "This sign-in account cannot use billing password recovery."
            )
        # Authentik does not filter by UID. Use its bounded email lookup, then
        # independently bind the result to the stored OIDC subject and email.
        lookup_query = urlencode({"email": expected_email} if field == "uid" else {"uuid": subject})
        value = await self.request("GET", f"/api/v3/core/users/?{lookup_query}&page_size=2")
        rows = value.get("results")
        pagination = value.get("pagination")
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
            or not isinstance(pagination, dict)
            or pagination.get("next") != 0
        ):
            raise AdministratorRecoveryUnavailableError(
                "This sign-in account cannot use billing password recovery."
            )
        user = rows[0]
        attributes = user.get("attributes")
        pk = user.get("pk")
        if (
            type(pk) is not int
            or pk < 1
            or user.get(field) != str(subject)
            or user.get("type") != "external"
            or user.get("path") not in ("bill/pending-registration", "bill/tenant-administrators")
            or user.get("is_active") is not True
            or user.get("is_superuser") is not False
            or user.get("groups") != []
            or user.get("roles") != []
            or not isinstance(user.get("email"), str)
            or user["email"].strip().casefold() != expected_email.strip().casefold()
            or not isinstance(attributes, dict)
            or attributes.get("billing_email_verified") is not True
            or (
                user.get("path") == "bill/tenant-administrators"
                and not self.valid_provision_marker(
                    attributes.get("billing_tenant_provision_command")
                )
            )
        ):
            raise AdministratorRecoveryUnavailableError(
                "This sign-in account cannot use billing password recovery."
            )
        expires = utcnow() + dt.timedelta(minutes=10)
        if delivery == "email":
            await self.request(
                "POST",
                f"/api/v3/core/users/{pk}/recovery_email/",
                {"token_duration": "minutes=10", "email_stage": str(self.email_stage)},
                no_content=True,
            )
            return None, expires
        response = await self.request(
            "POST", f"/api/v3/core/users/{pk}/recovery/", {"token_duration": "minutes=10"}
        )
        link = response.get("link")
        try:
            if (
                not isinstance(link, str)
                or len(link) > 2048
                or re.search(r"[\x00-\x20\x7f\\]", link)
            ):
                raise ValueError("invalid link")
            parsed = urlsplit(link)
            query = parse_qs(parsed.query, strict_parsing=True)
            if (
                parsed.scheme + "://" + parsed.netloc != self.base
                or parsed.path != "/if/flow/bill-administrator-recovery/"
                or parsed.fragment
                or set(query) != {"flow_token"}
                or len(query["flow_token"]) != 1
                or not re.fullmatch(r"[A-Za-z0-9_-]{20,512}", query["flow_token"][0])
            ):
                raise ValueError("untrusted recovery link")
        except ValueError:
            raise AdministratorRecoveryUnavailableError(
                "The sign-in provider returned an invalid recovery link."
            ) from None
        return link, expires

    @staticmethod
    def valid_provision_marker(value: object) -> bool:
        if not isinstance(value, str):
            return False
        try:
            return str(uuid.UUID(value)) == value
        except ValueError:
            return False
