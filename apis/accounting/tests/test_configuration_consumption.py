"""Company settings guide authoring without rewriting historical master values."""

import httpx
from billing_platform import reference
from billing_platform.db import tenant_scope
from billing_platform.db.reference_models import Currency
from billing_platform.ids import uuid7
from fastapi import FastAPI

from tests.conftest import TENANT, headers
from tests.test_masters import BASE, prepare


async def fields(client: httpx.AsyncClient, resource: str, **context: object) -> dict:
    result = await client.get(
        BASE + f"/configuration/{resource}/field-set?operation=create",
        headers=headers(**context),
    )
    assert result.status_code == 200, result.text
    return {field["key"]: field for field in result.json()["fields"]}


async def test_account_company_currency_and_conditional_controls(client: httpx.AsyncClient) -> None:
    await prepare(client)
    form = await fields(client, "accounts")
    assert form["currency_mode"]["control"]["choices"] == ["BASE", "FIXED"]
    assert form["currency"]["initial"] == "INR"
    assert form["currency"]["control"]["depends_on"] == {"currency_mode": ["FIXED"]}
    assert form["currency"]["control"]["reference_filters"] == {"company_currency": "true"}
    assert form["party_id"]["control"]["required_when_active"] is True
    assert form["rounding_limit"]["control"]["depends_on"] == {
        "rounding_method": ["NORMAL", "UP", "DOWN"]
    }
    enabled = await fields(client, "accounts", features={"multi_currency", "inventory"})
    assert "MULTI" in enabled["currency_mode"]["control"]["choices"]


async def test_withholding_choices_and_base_currency_default(client: httpx.AsyncClient) -> None:
    await prepare(client)
    form = await fields(client, "withholding-sections", features={"tds"})
    assert form["kind"]["control"]["choices"] == ["TDS"]
    rate = await fields(client, "withholding-rates", features={"tds"}, base_currency="USD")
    assert rate["threshold_currency"]["initial"] == "USD"
    assert rate["threshold_currency"]["control"]["reference_filters"] == {"base_only": "true"}
    disabled = await client.get(
        BASE + "/configuration/withholding-sections/field-set?operation=create",
        headers=headers(),
    )
    assert disabled.json()["can_create"] is False
    assert "TDS or TCS" in disabled.json()["unavailable_reason"]


async def test_profile_references_and_credit_dependency(client: httpx.AsyncClient) -> None:
    await prepare(client)
    for resource, kind in (("account-bank-profiles", "BANK"), ("account-tax-profiles", "TAX")):
        form = await fields(client, resource)
        assert form["account_id"]["control"]["reference_filters"] == {"kind": kind}
    credit = await fields(client, "party-credit-policies")
    assert credit["currency"]["initial"] == "INR"
    assert credit["currency"]["control"]["reference_filters"] == {"company_currency": "true"}
    assert credit["limit_amount"]["control"]["depends_on"] == {"limit_mode": ["LIMITED"]}
    assert credit["limit_amount"]["control"]["required_when_active"] is True


async def test_currency_picker_filters_new_choices_but_hydrates_history(
    client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    await prepare(client)
    await seed_currencies(app)
    path = BASE + "/configuration/options/currencies"
    base = await client.get(path + "?company_currency=true", headers=headers())
    assert base.status_code == 200, base.text
    assert [row["value"] for row in base.json()["items"]] == ["INR"]
    enabled = await client.get(
        path + "?company_currency=true",
        headers=headers(features={"multi_currency"}, allowed_currencies={"USD"}),
    )
    assert {row["value"] for row in enabled.json()["items"]} == {"INR", "USD"}
    historical = await client.get(path + "?company_currency=true&value=USD", headers=headers())
    assert [row["value"] for row in historical.json()["items"]] == ["USD"]


async def test_currency_cursor_invalidated_by_company_settings(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    await seed_currencies(app)
    path = BASE + "/configuration/options/currencies"
    first = await client.get(
        path + "?company_currency=true&limit=1", headers=headers(features={"multi_currency"})
    )
    cursor = first.json()["page"]["next_cursor"]
    assert cursor
    changed = await client.get(
        path,
        params={"company_currency": "true", "limit": 1, "cursor": cursor},
        headers=headers(),
    )
    assert changed.status_code in {409, 422}


async def seed_currencies(app: FastAPI) -> None:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add_all(
                Currency(**row)
                for row in reference.load("currency")
                if row["code"] in {"INR", "USD", "EUR"}
            )


async def test_history_filters_and_protected_controlling_fields(client: httpx.AsyncClient) -> None:
    await prepare(client)
    read = await client.get(BASE + "/configuration/accounts/field-set", headers=headers())
    mode = next(field for field in read.json()["fields"] if field["key"] == "currency_mode")
    assert "MULTI" in mode["control"]["choices"]
    from tests.conftest import COMPANY

    hidden = await fields(
        client,
        "accounts",
        policies=[
            {
                "entity_type": "accounting.account",
                "field_key": "kind",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
                "condition": None,
            }
        ],
    )
    assert hidden["party_id"]["control"]["disabled_reason"]
    assert hidden["party_id"]["control"]["depends_on"] == {}


async def test_company_bank_and_tax_registration_choices(client: httpx.AsyncClient) -> None:
    await prepare(client)
    bank_id, registration_id = uuid7(), uuid7()
    bank = await fields(client, "account-bank-profiles", bank_ids={bank_id})
    assert bank["company_bank_id"]["control"]["reference_values"] == [str(bank_id)]
    tax = await fields(
        client,
        "account-tax-profiles",
        registrations=[
            {
                "id": str(registration_id),
                "tax_system": "gst_in",
                "regime": "regular",
                "valid_from": "2020-01-01",
            }
        ],
    )
    assert tax["scheme"]["control"]["choices"] == ["GST_IN", "OTHER"]
    assert tax["company_registration_id"]["control"]["reference_values"] == [str(registration_id)]
    assert tax["component"]["control"]["choice_dependencies"]["CGST"] == {"scheme": ["GST_IN"]}


async def test_currency_notice_requires_a_readable_currency_field(
    client: httpx.AsyncClient,
) -> None:
    from tests.conftest import COMPANY

    await prepare(client)
    section = await client.get(
        BASE + "/configuration/withholding-sections/field-set?operation=create", headers=headers()
    )
    assert section.json()["notices"] == []
    masked = await client.get(
        BASE + "/configuration/accounts/field-set?operation=create",
        headers=headers(
            policies=[
                {
                    "entity_type": "accounting.account",
                    "field_key": "currency",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                    "condition": None,
                }
            ]
        ),
    )
    assert masked.json()["notices"] == []
