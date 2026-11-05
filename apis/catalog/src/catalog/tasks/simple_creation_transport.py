"""Forward fresh gateway authority to native owners; never persist credentials."""

from collections.abc import Mapping
from typing import Any

import httpx
from billing_platform.errors import PlatformError
from fastapi import FastAPI


class ServiceUnavailableError(PlatformError):
    status_code = 503
    code = "service_unavailable"


class OwnerRejectedError(PlatformError):
    def __init__(self, status: int, error: dict[str, Any]) -> None:
        super().__init__(
            str(error.get("message", "Product setup could not continue")),
            **({"fields": error["fields"]} if error.get("fields") else {}),
        )
        self.status_code = status
        self.code = str(error.get("code", "validation_failed"))
        self.definite = (
            status < 500 and status not in {408, 429} and "busy" not in self.message.lower()
        )


class CreationOwners:
    def __init__(self, app: FastAPI, headers: Mapping[str, str], origins: dict[str, str]) -> None:
        self.app, self.origins = app, origins
        self.headers = {
            key: value
            for key, value in headers.items()
            if key.lower()
            in {
                "x-actor-context",
                "x-actor-signature",
                "x-company-context",
                "x-company-signature",
                "x-trace-id",
                "x-request-id",
                "authorization",
                "x-company-step-up",
            }
        }

    async def call(
        self,
        service: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        origin = "http://catalog.local" if service == "catalog" else self.origins.get(service)
        if origin is None:
            raise ServiceUnavailableError(
                "Configure product opening owner connections before saving stock"
            )
        transport = httpx.ASGITransport(app=self.app) if service == "catalog" else None
        headers = self.headers | ({"Idempotency-Key": key} if key else {})
        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=70 if path.endswith("/batch-prices") else 10,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.request(method, origin + path, headers=headers, json=body)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceUnavailableError(
                "Product setup is saved; retry to check its progress"
            ) from exc
        if response.status_code >= 300 or not isinstance(payload, dict):
            if response.status_code >= 400 and isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    raise OwnerRejectedError(response.status_code, error)
            raise ServiceUnavailableError("The product owner returned an invalid response")
        return payload
