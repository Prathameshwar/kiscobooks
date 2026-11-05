import pytest
from billing_platform.ids import uuid7

from tests.test_api import headers
from tests.test_classification_api import setup_source

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_type_controls_follow_verified_company_features(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    result = await client.get(
        f"/v1/companies/{company}/entities/catalog.product_type_revision/field-set",
        params={"operation": "create"},
        headers=headers(
            company,
            tenant=tenant_a,
            user=user,
            permission=["product_type.read", "product_type.manage"],
        ),
    )
    assert result.status_code == 200, result.text
    fields = {field["key"]: field for field in result.json()["fields"]}
    assert [row["value"] for row in fields["tracking_modes"]["control"]["choices"]] == ["NONE"]
    assert fields["require_expiry"]["control"]["disabled_reason"]
    assert fields["require_expiry"]["suggested_value"] == "false"


async def test_inventory_controls_explain_unavailable_tracking(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    result = await client.get(
        f"/v1/companies/{company}/entities/catalog.inventory_profile_template_revision/field-set",
        params={"operation": "create"},
        headers=headers(
            company,
            tenant=tenant_a,
            user=user,
            permission=["inventory_profile_template.read", "inventory_profile_template.manage"],
        ),
    )
    assert result.status_code == 200, result.text
    fields = {field["key"]: field for field in result.json()["fields"]}
    for key in ("lot_tracking", "serial_tracking", "expiry_required"):
        assert fields[key]["control"]["disabled_reason"]
        assert fields[key]["suggested_value"] == "false"


async def test_unit_conversion_controls_and_price_levels_follow_company_context(
    client, factory, tenant_a
):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "item.read",
            "item.update",
            "product_configuration.read",
            "product_configuration.manage",
        ],
    )
    root = f"/v1/companies/{company}/entities/catalog."
    response = await client.get(
        root + "item_unit_revision/field-set", params={"operation": "create"}, headers=current
    )
    assert response.status_code == 200, response.text
    fields = {field["key"]: field for field in response.json()["fields"]}
    for key, mode in (
        ("numerator", "FIXED"),
        ("denominator", "FIXED"),
        ("nominal_ratio", "MEASURED"),
        ("secondary_unit_id", "MEASURED"),
    ):
        assert fields[key]["control"]["depends_on"] == "conversion_mode"
        assert fields[key]["control"]["show_when"] == mode
    response = await client.get(
        root + "product_pricing_policy/field-set", params={"operation": "create"}, headers=current
    )
    assert response.status_code == 200, response.text
    fields = {field["key"]: field for field in response.json()["fields"]}
    assert fields["sale_level_count"]["control"]["maximum"] == 1
