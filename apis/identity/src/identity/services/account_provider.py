"""Fixed, object-scoped Authentik adapter. Passwords and role changes are excluded."""

from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from billing_platform.errors import PlatformError
from billing_platform.provider_http import ProviderHttpError, provider_json

from identity.config import Settings
from identity.domain.account_review import Applicant, eligible


class AccountProviderUnavailableError(PlatformError):
    status_code = 503
    code = "account_provider_unavailable"


class AccountProvider:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.http = http
        base = urlsplit(settings.authentik_review_url or "")
        if (
            base.scheme != "https"
            or not base.hostname
            or base.username
            or base.password
            or base.query
            or base.fragment
            or not settings.authentik_review_token
        ):
            raise AccountProviderUnavailableError("Account review integration needs configuration.")
        self.base = (settings.authentik_review_url or "").rstrip("/")
        self.headers = {
            "Authorization": "Bearer " + settings.authentik_review_token.get_secret_value()
        }

    async def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            return await provider_json(
                self.http,
                method,
                self.base + path,
                headers=self.headers,
                body=body,
                max_bytes=2_000_000,
            )
        except ProviderHttpError:
            raise AccountProviderUnavailableError(
                "Account provider is unavailable. The saved decision can be retried."
            ) from None

    @staticmethod
    def applicant(value: dict[str, Any]) -> Applicant:
        try:
            if value.get("is_superuser") is True:
                raise ValueError("privileged account")
            attributes = value.get("attributes")
            if attributes is None:
                attributes = {}
            if type(value.get("is_active")) is not bool or not isinstance(attributes, dict):
                raise ValueError("invalid activation or attributes")
            region = attributes.get("billing_registration_region")
            if region is None:
                region = {}
            if not isinstance(region, dict):
                raise ValueError("invalid registration region")
            workspace_name = attributes.get("billing_registration_workspace_name")
            if workspace_name is not None and (
                not isinstance(workspace_name, str)
                or len(workspace_name) > 200
                or any(ord(char) < 32 or ord(char) == 127 for char in workspace_name)
            ):
                raise ValueError("invalid workspace request")
            row = Applicant(
                provider_id=int(value["pk"]),
                provider_uuid=uuid.UUID(value["uuid"]),
                name=value["name"],
                username=value["username"],
                email=value["email"],
                path=value["path"],
                user_type=value["type"],
                is_active=value["is_active"],
                verified=attributes.get("billing_email_verified") is True,
                groups=tuple(value.get("groups") or []),
                roles=tuple(str(role) for role in value.get("roles") or []),
                country_code=region.get("country_code", ""),
                state_code=region.get("state_code", ""),
                workspace_name=workspace_name,
            )
            if (
                not eligible(row)
                or len(row.name) > 200
                or len(row.username) > 150
                or len(row.email) > 320
                or len(row.country_code) > 2
                or len(row.state_code) > 6
            ):
                raise ValueError("ineligible account")
            return row
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise AccountProviderUnavailableError(
                "This account is outside the supported registration scope."
            ) from exc

    @staticmethod
    def subject(value: dict[str, Any]) -> str:
        # The configured Bill OIDC provider uses Authentik hashed_user_id mode:
        # IDToken._resolve_sub returns User.uid, not User.uuid.
        uid = value.get("uid")
        if not isinstance(uid, str) or re.fullmatch(r"[0-9a-f]{64}", uid) is None:
            raise AccountProviderUnavailableError("Registration subject could not be confirmed.")
        return uid

    async def page(self, page: int = 1) -> tuple[list[Applicant], bool]:
        value = await self.request(
            "GET",
            f"/api/v3/core/users/?path=bill%2Fpending-registration&page_size=100&page={page}&ordering=-pk",
        )
        results = value.get("results")
        if not isinstance(results, list) or len(results) > 100:
            raise AccountProviderUnavailableError(
                "Unexpected registration response. Contact your administrator."
            )
        rows = []
        for raw in results:
            try:
                rows.append(self.applicant(raw))
            except AccountProviderUnavailableError:
                # A provider administrator may have removed an account from eligibility.
                continue
        pagination = value.get("pagination")
        # Authentik 2026.8 uses 0 for the last page and a positive next-page number.
        if (
            not isinstance(pagination, dict)
            or type(pagination.get("next")) is not int
            or not 0 <= pagination["next"] <= 10000
        ):
            raise AccountProviderUnavailableError("Unexpected registration pagination.")
        return rows, pagination["next"] != 0

    async def pending_email(self, email: str) -> list[Applicant]:
        """Read the provider's exact pending email before creating an invited tenant."""
        query = urlencode(
            {
                "path": "bill/pending-registration",
                "email": email,
                "page_size": 100,
                "page": 1,
            }
        )
        value = await self.request("GET", "/api/v3/core/users/?" + query)
        results, pagination = value.get("results"), value.get("pagination")
        if not isinstance(results, list) or len(results) > 100 or not isinstance(pagination, dict):
            raise AccountProviderUnavailableError("Unexpected registration lookup response.")
        if pagination.get("next") != 0:
            raise AccountProviderUnavailableError("Registration lookup is ambiguous.")
        pending: list[Applicant] = []
        for raw in results:
            try:
                observed = self.applicant(raw)
            except AccountProviderUnavailableError:
                continue
            if (
                observed.email.casefold() == email.casefold()
                and not observed.is_active
                and not observed.verified
            ):
                pending.append(observed)
        return pending

    async def read(self, provider_id: int) -> tuple[Applicant, dict[str, Any]]:
        value = await self.request("GET", f"/api/v3/core/users/{provider_id}/")
        row = self.applicant(value)
        if row.provider_id != provider_id:
            raise AccountProviderUnavailableError("Registration identity changed.")
        return row, value

    async def apply(
        self,
        provider_id: int,
        raw: dict[str, Any],
        *,
        active: bool,
        verified: bool,
        command_id: uuid.UUID,
    ) -> None:
        attributes = dict(raw.get("attributes") or {})
        attributes["billing_email_verified"] = verified
        attributes["billing_account_review_command"] = str(command_id)
        await self.request(
            "PATCH",
            f"/api/v3/core/users/{provider_id}/",
            {"is_active": active, "attributes": attributes},
        )
