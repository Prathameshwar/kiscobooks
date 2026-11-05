"""Authentik boundary for immediate tenant administrator provisioning.

The token belongs to a dedicated service account. Never include a password in a
provider error, log, audit record, idempotency receipt or notification event.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from billing_platform.errors import ConflictError, PlatformError
from billing_platform.provider_http import ProviderHttpError, provider_json

from identity.config import Settings


class AdministratorProviderUnavailableError(PlatformError):
    code = "administrator_provider_unavailable"
    status_code = 503


class AdministratorProvider:
    @staticmethod
    def username_for(email: str) -> str:
        # Stable across request keys so concurrent creates for one email cannot
        # produce two distinct provider usernames.
        return "bill-admin-" + hashlib.sha256(email.strip().casefold().encode()).hexdigest()[:32]

    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        base = urlsplit(settings.authentik_provision_url or "")
        if (
            base.scheme != "https"
            or not base.hostname
            or base.username
            or base.password
            or base.query
            or base.fragment
            or base.path not in ("", "/")
            or not settings.authentik_provision_token
        ):
            raise AdministratorProviderUnavailableError(
                "Administrator provisioning is not configured."
            )
        self.base = (settings.authentik_provision_url or "").rstrip("/")
        self.headers = {
            "Authorization": "Bearer " + settings.authentik_provision_token.get_secret_value()
        }
        self.http = http

    async def request(
        self, method: str, path: str, body: dict[str, Any] | None = None, *, status: int = 200
    ) -> dict[str, Any]:
        try:
            return await provider_json(
                self.http,
                method,
                self.base + path,
                headers=self.headers,
                body=body,
                max_bytes=65536,
                expected_status=status,
            )
        except ProviderHttpError:
            raise AdministratorProviderUnavailableError(
                "Authentik could not confirm provisioning. Retry with the same request key."
            ) from None

    @staticmethod
    def confirm(row: dict[str, Any], email: str) -> tuple[int, str]:
        uid, pk, attributes = row.get("uid"), row.get("pk"), row.get("attributes")
        if (
            type(pk) is not int
            or pk < 1
            or not isinstance(uid, str)
            or re.fullmatch(r"[0-9a-f]{64}", uid) is None
            or not isinstance(row.get("email"), str)
            or row["email"].strip().casefold() != email.strip().casefold()
            or row.get("type") != "external"
            or row.get("is_active") is not True
            or row.get("is_superuser") is not False
            or row.get("groups")
            or row.get("roles")
            or not isinstance(attributes, dict)
            or attributes.get("billing_email_verified") is not True
        ):
            raise ConflictError("The selected Authentik account is not an active verified user.")
        return pk, uid

    @staticmethod
    def confirm_created(row: dict[str, Any], email: str, marker: uuid.UUID) -> tuple[int, str]:
        attributes = row.get("attributes")
        if (
            row.get("username") != AdministratorProvider.username_for(email)
            or row.get("path") != "bill/tenant-administrators"
            or type(row.get("is_active")) is not bool
            or not isinstance(attributes, dict)
            or attributes.get("billing_tenant_provision_command") != str(marker)
            or attributes.get("billing_email_verified") is not True
        ):
            raise ConflictError(
                "The Authentik provisioning account changed. Review it before retrying."
            )
        checked = {**row, "is_active": True}
        return AdministratorProvider.confirm(checked, email)

    async def by_email(self, email: str) -> dict[str, Any] | None:
        query = urlencode({"email": email, "page_size": 100, "page": 1})
        result = await self.request("GET", "/api/v3/core/users/?" + query)
        rows, pagination = result.get("results"), result.get("pagination")
        if (
            not isinstance(rows, list)
            or not isinstance(pagination, dict)
            or pagination.get("next") != 0
        ):
            raise AdministratorProviderUnavailableError("Authentik account lookup is ambiguous.")
        exact = [
            row
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("email"), str)
            and row["email"].strip().casefold() == email.strip().casefold()
        ]
        if len(exact) > 1:
            raise ConflictError(
                "Several sign-in accounts use this email. Resolve them in Authentik first."
            )
        return exact[0] if exact else None

    async def create(
        self, *, email: str, name: str, password: str, marker: uuid.UUID
    ) -> tuple[str, str]:
        username = self.username_for(email)
        row = await self.by_email(email)
        if row is not None:
            if row.get("username") != username:
                raise ConflictError(
                    "An Authentik account already uses this email. Select it instead."
                )
            created = row
        else:
            created = await self.request(
                "POST",
                "/api/v3/core/users/",
                {
                    "username": username,
                    "name": name,
                    "email": email,
                    "type": "external",
                    "path": "bill/tenant-administrators",
                    "is_active": False,
                    "attributes": {
                        "billing_email_verified": True,
                        "billing_tenant_provision_command": str(marker),
                    },
                    "groups": [],
                    "roles": [],
                },
                status=201,
            )
        pk, uid = self.confirm_created(created, email, marker)
        if created["is_active"] is False:
            await self.request(
                "POST", f"/api/v3/core/users/{pk}/set_password/", {"password": password}, status=204
            )
        return username, uid

    async def activate(self, *, email: str, marker: uuid.UUID, subject: str) -> None:
        row = await self.by_email(email)
        if row is None:
            raise AdministratorProviderUnavailableError(
                "Provisioned Authentik account disappeared."
            )
        pk, observed = self.confirm_created(row, email, marker)
        if observed != subject:
            raise ConflictError("The Authentik account identity changed before activation.")
        if row["is_active"] is False:
            await self.request("PATCH", f"/api/v3/core/users/{pk}/", {"is_active": True})
        verified = await self.request("GET", f"/api/v3/core/users/{pk}/")
        _, observed = self.confirm(verified, email)
        if observed != subject:
            raise ConflictError(
                "Authentik activation readback did not match the tenant administrator."
            )
