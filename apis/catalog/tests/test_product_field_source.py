"""Identity-to-Catalog product definition wire contract, using the real owner process."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.projections import CustomFieldDefinitionProjection
from catalog.tasks.field_context import custom_definition
from catalog.tasks.identity_source import IdentitySourceSettings, fetch_identity_snapshot
from catalog.tasks.product_field_rollout import source_definition_digests
from catalog.tasks.projections import activate_snapshot
from tests.test_identity_source_integration import identity_server as identity_server


async def test_authored_product_digest_and_typed_default_survive_real_source_sync(
    identity_server: tuple[IdentitySourceSettings, dict[str, Any]],  # noqa: F811
    factory: async_sessionmaker[AsyncSession],
) -> None:
    settings, info = identity_server
    tenant, company = uuid.UUID(info["tenant_id"]), uuid.UUID(info["company_id"])
    raw = json.dumps(
        {
            "issued_at": int(time.time()),
            "tenant_id": str(tenant),
            "user_id": info["user_id"],
            "grants": [
                {
                    "permissions": ["custom_field.manage"],
                    "scope_type": "tenant",
                    "scope_id": None,
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                    "is_active": True,
                }
            ],
        }
    ).encode()
    auth = {
        "x-actor-context": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        "x-actor-signature": hmac.new(
            info["actor_secret"].encode(), raw, hashlib.sha256
        ).hexdigest(),
    }
    async with httpx.AsyncClient(base_url=settings.base_url, trust_env=False) as owner:
        response = await owner.post(
            "/v1/custom-field-definitions",
            headers=auth,
            json={
                "entity_type": "catalog.item",
                "company_id": str(company),
                "label": "Count",
                "definition": {"key": "cf_count", "data_type": "integer", "default_value": 7},
            },
        )
    assert response.status_code == 201, response.text
    authored = response.json()
    source = await fetch_identity_snapshot(
        settings, tenant_id=tenant, company_id=company, request_id=uuid7()
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(db, source)
            digests = await source_definition_digests(db, company, "catalog.item")
            assert digests == {authored["id"]: authored["digest"]}
            row = await db.scalar(
                select(CustomFieldDefinitionProjection).where(
                    CustomFieldDefinitionProjection.source_id == uuid.UUID(authored["id"])
                )
            )
            assert row is not None and row.requires_adoption
            assert custom_definition(row).default_value == 7
