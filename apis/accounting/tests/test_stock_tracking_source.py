"""Catalog source transport verifies ownership, publication and protected required facts."""

import datetime as dt
import time
from typing import Any

import httpx
import pytest
from billing_platform.company_context import CompanyContext
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from pydantic import SecretStr

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.tasks.stock_tracking_source import TrackingSourceUnavailableError, tracking_source
from tests.conftest import COMPANY, TENANT, USER


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "owner",
        "publication",
        "protected",
        "requirements",
        "unit",
        "permission",
        "unconfigured",
        "profile_owner",
        "requirement_range",
        "activated_owner",
        "protected_optional",
    ],
)
async def test_verified_product_source(monkeypatch: pytest.MonkeyPatch, fault: str | None) -> None:
    item, profile, identifiers, unit, owner = uuid7(), uuid7(), uuid7(), uuid7(), uuid7()
    family, activated = uuid7(), uuid7()
    day = dt.date(2026, 10, 28)
    company = str(COMPANY)
    routes: dict[str, dict[str, Any]] = {
        f"items/{item}": {
            "id": str(item),
            "company_id": company,
            "status": "ACTIVE",
            "base_unit_id": str(unit),
            "family_id": str(family),
        },
        f"product-families/{family}": {
            "id": str(family),
            "company_id": company,
            "status": "ACTIVE",
            "kind": "GOODS",
        },
        "item-inventory-profiles": {
            "items": [{"id": str(activated), "item_id": str(item)}],
            "page": {"has_more": False},
        },
        f"items/{item}/configuration": {
            "company_id": company,
            "as_of": day.isoformat(),
            "kind": "GOODS",
            "profiles": {"inventory_template_revision_id": str(profile)},
        },
        "product-configuration/options/inventory-template-revisions": {
            "items": [{"value": str(profile), "parent_id": str(owner)}]
        },
        f"inventory-templates/{owner}/revisions/{profile}": {
            "id": str(profile),
            "company_id": company,
            "published_at": "2026-10-01T00:00:00Z",
            "template_id": str(owner),
            "identifier_profile_id": str(identifiers),
            "lot_tracking": True,
            "serial_tracking": True,
            "expiry_required": True,
            "manufacture_date_required": True,
            "shelf_life_days": None,
            "minimum_remaining_life_days": None,
        },
        f"identifier-profiles/{identifiers}": {
            "id": str(identifiers),
            "company_id": company,
            "is_active": True,
            "normalization_version": 1,
        },
        f"identifier-profiles/{identifiers}/requirements": {
            "items": [
                {
                    "profile_id": str(identifiers),
                    "identifier_type": "SERIAL",
                    "namespace_rule": "COMPANY",
                    "min_count": 1,
                    "max_count": 1,
                    "requires_slot": False,
                }
            ],
            "page": {"has_more": False, "next_cursor": None},
        },
        f"units/{unit}": {
            "id": str(unit),
            "company_id": company,
            "dimension": "COUNT",
            "decimal_places": 0,
            "quantity_increment": "1.0000",
            "is_active": True,
        },
    }
    routes[f"item-inventory-profiles/{activated}"] = {
        **routes[f"inventory-templates/{owner}/revisions/{profile}"],
        "id": str(activated),
        "item_id": str(item),
        "base_unit_id": str(unit),
        "template_revision_id": str(profile),
    }
    if fault == "owner":
        routes[f"items/{item}"]["company_id"] = str(uuid7())
    if fault == "publication":
        routes[f"inventory-templates/{owner}/revisions/{profile}"]["published_at"] = None
    if fault == "protected":
        routes[f"inventory-templates/{owner}/revisions/{profile}"].pop("lot_tracking")
    if fault == "requirements":
        routes[f"identifier-profiles/{identifiers}/requirements"]["page"]["has_more"] = True
    if fault == "unit":
        routes[f"units/{unit}"]["decimal_places"] = 3
    if fault == "profile_owner":
        routes[f"inventory-templates/{owner}/revisions/{profile}"]["template_id"] = str(uuid7())
    if fault == "requirement_range":
        routes[f"identifier-profiles/{identifiers}/requirements"]["items"][0]["min_count"] = 2
    if fault == "activated_owner":
        routes[f"item-inventory-profiles/{activated}"]["company_id"] = str(uuid7())
    if fault == "protected_optional":
        routes[f"inventory-templates/{owner}/revisions/{profile}"].pop(
            "minimum_remaining_life_days"
        )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer ephemeral-test-caller"
        assert request.headers["x-company-step-up"] == "ephemeral-test-proof"
        assert request.url.host == "catalog.example.test"
        key = request.url.path.split(f"/v1/companies/{COMPANY}/", 1)[1]
        calls.append(key)
        if fault == "permission":
            return httpx.Response(403, json={"error": {"code": "permission_denied"}})
        return httpx.Response(200, json=routes[key])

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr("ephemeral-stock-source-test-secret"),
        stock_catalog_url=None
        if fault == "unconfigured"
        else "https://catalog.example.test/catalog",
    )
    access = Access(
        Actor(TENANT, USER),
        CompanyContext(
            issued_at=int(time.time()),
            tenant_id=TENANT,
            company_id=COMPANY,
            user_id=USER,
            base_currency="INR",
        ),
    )
    expected = (
        PermissionDeniedError
        if fault == "permission"
        else ValidationFailedError
        if fault == "owner"
        else TrackingSourceUnavailableError
    )
    if fault:
        with pytest.raises(expected):
            await tracking_source(
                settings, access, item, day, "Bearer ephemeral-test-caller", "ephemeral-test-proof"
            )
    else:
        result = await tracking_source(
            settings, access, item, day, "Bearer ephemeral-test-caller", "ephemeral-test-proof"
        )
        assert result.item_id == item and result.company_id == COMPANY
        assert result.lot_tracking and result.serial_tracking
        assert result.requirements[0].namespace_rule == "COMPANY"
        assert len(calls) == 9 and len(result.source_digest) == 64
        assert not any("/configuration" in call for call in calls)


def test_tracking_gateway_prefix_is_supported_but_signed_stock_owner_requires_origin():
    from pydantic import ValidationError

    settings = dict(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr("ephemeral-stock-origin-test-secret"),
    )
    assert Settings(
        **settings, stock_catalog_url="http://127.0.0.1:8090/catalog"
    ).stock_catalog_url.endswith("/catalog")
    with pytest.raises(ValidationError):
        Settings(**settings, stock_owner_url="http://127.0.0.1:8090/catalog")
