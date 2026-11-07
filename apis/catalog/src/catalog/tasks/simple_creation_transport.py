"""Forward fresh gateway authority to native owners; never persist credentials."""

import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.errors import PlatformError
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import ServiceKey, service_request_bytes, sign_service_body
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
            status < 500
            and status not in {408, 429}
            and "busy" not in self.message.lower()
            and not (
                status == 409
                and self.message
                == "stock posting is using these definitions; retry after it completes"
            )
        )


class CreationOwners:
    def __init__(
        self,
        app: FastAPI,
        headers: Mapping[str, str],
        origins: dict[str, str],
        source_delivery: Any = None,
    ) -> None:
        self.app, self.origins = app, origins
        self.source_delivery = source_delivery
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

    async def item_source_bundle(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        item_id: uuid.UUID,
        creation_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Build only the new item's signed-owner facts, never browser-authored facts."""
        from sqlalchemy import select

        from catalog.api.voucher_sources import facts
        from catalog.models.products import Item

        masters: list[dict[str, Any]] = []
        with tenant_scope(tenant_id):
            async with self.app.state.session_factory() as db:
                item = await db.scalar(
                    select(Item).where(
                        Item.company_id == company_id, Item.id == item_id, Item.status == "ACTIVE"
                    )
                )
                if item is None:
                    raise ServiceUnavailableError("Activated product evidence is not ready")
                for entity in (
                    "item",
                    "item_transaction_policy",
                    "item_unit_revision",
                    "item_regulatory_classification",
                ):
                    bundle, cursor = await facts(
                        db, tenant_id, company_id, entity, None, 128, item_id
                    )
                    if cursor is not None:
                        raise ServiceUnavailableError("Product source evidence exceeds its bound")
                    masters.extend(bundle["masters"])
                unit, _ = await facts(
                    db, tenant_id, company_id, "unit", None, 1, unit_id=item.base_unit_id
                )
                masters.extend(unit["masters"])
        if not any(row["entity_type"] == "item_unit_revision" for row in masters):
            raise ServiceUnavailableError("Product unit evidence is not ready")
        return {
            "message_id": str(uuid.uuid5(creation_id, "catalog-item-source")),
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "definitions": [],
            "masters": masters,
        }

    async def deliver_source(self, bundle: dict[str, Any]) -> dict[str, Any]:
        credential = self.source_delivery
        origin = self.origins.get("vouchers")
        if credential is None or origin is None:
            raise ServiceUnavailableError("Product source delivery is not configured")
        path = "/internal/v1/sources"
        raw = canonical_json(bundle)
        stamp = int(time.time())
        operation = "vouchers.sources.apply"
        key = ServiceKey(
            "catalog",
            "vouchers",
            frozenset({operation}),
            credential.secret.get_secret_value().encode(),
        )
        headers = {
            "Content-Type": "application/json",
            "X-Service-Key-Id": credential.key_id,
            "X-Service-Issuer": "catalog",
            "X-Service-Timestamp": str(stamp),
            "X-Service-Signature": sign_service_body(
                key,
                key_id=credential.key_id,
                operation=operation,
                timestamp=stamp,
                body=service_request_bytes(method="POST", path=path, query="", body=raw),
            ),
        }
        try:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.post(origin + path, content=raw, headers=headers)
            if response.status_code != 200:
                raise ServiceUnavailableError("Vouchers has not accepted product source evidence")
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("invalid source receipt")
            return result
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceUnavailableError(
                "Product source delivery is saved; retry to verify it"
            ) from exc
