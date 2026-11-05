"""Configuration fixtures use real signed Identity policy sources."""

import datetime as dt
import uuid
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers


async def seed_legacy_configuration(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    kind: str,
    owner: uuid.UUID,
    *,
    options: dict[str, Any] | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Pre-upgrade fixture only: the public API cannot create these retired records."""
    from catalog.models import (
        CatalogDefaultProfile,
        ProductConfigurationDraft,
        ProductConfigurationRevision,
        ProductConfigurationScope,
        ProductEntryOptionPolicy,
        ProductPricingPolicy,
    )
    from catalog.schemas.configuration import EntryOptions, PricingRequirements, ProfileDefaults

    field = {
        "TYPE": "product_type_id",
        "GROUP": "group_id",
        "FAMILY": "family_id",
        "SKU": "item_id",
    }[kind]
    common = {"tenant_id": tenant, "company_id": company}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            scope = ProductConfigurationScope(
                **common, scope_kind=kind, owner_id=owner, latest_revision=1, **{field: owner}
            )
            db.add(scope)
            await db.flush()
            draft = ProductConfigurationDraft(
                **common,
                scope_id=scope.id,
                status="PUBLISHED",
                effective_from=dt.date(2090, 1, 1),
                change_reason="Legacy publication",
            )
            db.add(draft)
            await db.flush()
            pending = ProductConfigurationDraft(
                **common,
                scope_id=scope.id,
                status="DRAFT",
                effective_from=dt.date(2091, 1, 1),
                change_reason="Unpublished legacy draft",
            )
            db.add(pending)
            await db.flush()
            revision = ProductConfigurationRevision(
                **common,
                scope_id=scope.id,
                source_draft_id=draft.id,
                revision=1,
                effective_from=draft.effective_from,
                change_reason=draft.change_reason,
                published_at=utcnow(),
            )
            db.add(revision)
            await db.flush()
            for key, value in (
                ("draft_id", draft.id),
                ("draft_id", pending.id),
                ("revision_id", revision.id),
            ):
                db.add_all(
                    [
                        ProductEntryOptionPolicy(
                            **common, **{key: value}, **EntryOptions(**(options or {})).model_dump()
                        ),
                        CatalogDefaultProfile(
                            **common, **{key: value}, **ProfileDefaults().model_dump()
                        ),
                        ProductPricingPolicy(
                            **common, **{key: value}, **PricingRequirements().model_dump()
                        ),
                    ]
                )
            return scope.id, pending.id, revision.id


async def setup_configuration(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], dict[str, Any]]:
    company, user, _, product = await setup_product(factory, tenant)
    return (
        company,
        user,
        headers(company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS)),
        product,
    )


async def publish_configuration(
    client: httpx.AsyncClient,
    base: str,
    auth: dict[str, str],
    *,
    effective_from: str = "2090-01-01",
    scope_id: str | None = None,
    scope: dict[str, Any] | None = None,
    **values: Any,
) -> tuple[str, dict[str, Any]]:
    if scope_id is None:
        created = await client.post(
            base + "/product-configuration-scopes",
            headers=command_headers(auth),
            json=scope or {"scope_kind": "COMPANY"},
        )
        assert created.status_code == 201, created.text
        scope_id = created.json()["id"]
    draft = await client.post(
        base + "/product-configurations",
        headers=command_headers(auth),
        json={
            "scope_id": scope_id,
            "effective_from": effective_from,
            "change_reason": "Reviewed",
            **values,
        },
    )
    assert draft.status_code == 201, draft.text
    path = base + "/product-configurations/" + draft.json()["id"]
    preview = await client.get(path + "/preview", headers=auth)
    assert preview.status_code == 200, preview.text
    value = preview.json()
    revision = await client.post(
        path + "/publish",
        headers=command_headers(auth),
        json={
            "expected_version": value["draft_version"],
            "expected_generation": value["policy_generation"],
            "expected_source_version": value["source_version"],
        },
    )
    assert revision.status_code == 201, revision.text
    assert scope_id is not None
    return scope_id, revision.json()
