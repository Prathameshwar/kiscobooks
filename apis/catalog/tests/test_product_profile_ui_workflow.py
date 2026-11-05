"""UI-shaped payloads exercise the existing native revision and publication pipeline."""

import pytest
from billing_platform.ids import uuid7

from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
PROFILES = [
    (
        "inventory-templates",
        "inventory_profile_template",
        "template_id",
        {
            "identifier_profile_id": None,
            "lot_tracking": True,
            "serial_tracking": True,
            "expiry_required": True,
            "manufacture_date_required": False,
            "shelf_life_days": 30,
            "minimum_remaining_life_days": 0,
            "issue_strategy": "FEFO",
            "valuation_method": "SPECIFIC",
            "negative_stock_policy": "BLOCK",
        },
        {"negative_stock_policy": "WARN"},
    ),
    (
        "warranty-policies",
        "warranty_policy",
        "policy_id",
        {
            "duration": 12,
            "duration_unit": "MONTHS",
            "start_trigger": "SALE",
            "coverage_description": "Manufacturing defects.\nKeep proof of purchase.",
        },
        {"duration": 24},
    ),
    (
        "return-policies",
        "return_policy",
        "policy_id",
        {
            "returns_allowed": True,
            "window_days": 0,
            "condition_codes": ["UNUSED", "PROOF_OF_PURCHASE"],
        },
        {"condition_codes": ["UNDAMAGED", "PROOF_OF_PURCHASE"]},
    ),
    (
        "handling-profiles",
        "handling_profile",
        "profile_id",
        {
            "temperature_min": "-273.1500",
            "temperature_max": "4.1234",
            "temperature_unit": "CELSIUS",
            "fragile": True,
            "keep_dry": True,
            "keep_upright": False,
            "instructions": "Cold storage.\nKeep dry.",
        },
        {"instructions": "Keep dry.\nUse care."},
    ),
]


@pytest.mark.parametrize("resource,prefix,parent,payload,patch", PROFILES)
async def test_ui_native_profile_workflow(
    client, factory, tenant_a, resource, prefix, parent, payload, patch
):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            prefix + ".read",
            prefix + ".manage",
            prefix + ".publish",
            "product_configuration.read",
        ],
    )
    root = f"/v1/companies/{company}/{resource}"
    identity = await client.post(
        root,
        headers=command_headers(current),
        json={"code": "STANDARD", "name": "Standard profile"},
    )
    assert identity.status_code == 201, identity.text
    master = root + "/" + identity.json()["id"]
    route = master + "/revisions"
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=payload)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row[parent] == identity.json()["id"] and row["company_id"] == str(company)
    assert row["row_version"] == 1 and row["revision"] == 1 and row["published_at"] is None
    replayed = await client.post(route, headers=receipt, json=payload)
    assert replayed.status_code == 201 and replayed.headers["Idempotency-Replayed"] == "true"
    detail = route + "/" + row["id"]
    source = {
        "inventory-templates": "inventory-template-revisions",
        "warranty-policies": "warranty-revisions",
        "return-policies": "return-policy-revisions",
        "handling-profiles": "handling-revisions",
    }[resource]
    options = (
        f"/v1/companies/{company}/product-configuration/options/{source}?value={row['id']}&limit=1"
    )
    draft_options = await client.get(options, headers=current)
    assert draft_options.status_code == 200 and draft_options.json()["items"] == []
    history = await client.get(route, headers=current, params={"sort": "-revision", "limit": 25})
    assert history.status_code == 200 and history.json()["items"][0]["id"] == row["id"]
    renamed = await client.patch(
        master, headers=command_headers(current), json={"expected_version": 1, "code": "OTHER"}
    )
    assert renamed.status_code == 409
    updated = await client.patch(
        detail, headers=command_headers(current), json={"expected_version": 1, **patch}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["row_version"] == 2
    if resource == "handling-profiles":
        assert updated.json()["temperature_min"] == "-273.1500"
        assert updated.json()["temperature_max"] == "4.1234"
    if resource == "return-policies":
        conditions = await client.get(detail + "/conditions?limit=5&sort=id", headers=current)
        assert conditions.status_code == 200 and not conditions.json()["page"]["has_more"]
        assert {item["condition_code"] for item in conditions.json()["items"]} == set(
            patch["condition_codes"]
        )
        assert updated.json()["window_days"] == 0
    manager = headers(
        company, tenant=tenant_a, user=user, permission=[prefix + ".read", prefix + ".manage"]
    )
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(manager), json={"expected_version": 2}
        )
    ).status_code == 403
    publisher = headers(
        company, tenant=tenant_a, user=user, permission=[prefix + ".read", prefix + ".publish"]
    )
    published = await client.post(
        detail + "/publish", headers=command_headers(publisher), json={"expected_version": 2}
    )
    assert published.status_code == 200, published.text
    assert published.json()["published_at"] is not None and published.json()["row_version"] == 3
    published_options = await client.get(options, headers=current)
    assert published_options.status_code == 200, published_options.text
    assert published_options.json()["items"][0]["value"] == row["id"]
    assert published_options.json()["items"][0]["parent_id"] == identity.json()["id"]
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 3, **patch}
        )
    ).status_code == 409
