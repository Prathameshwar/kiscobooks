"""Native contracts needed by the ten accounting master screens."""

import httpx
from billing_platform.ids import uuid7

from tests.conftest import COMPANY, headers
from tests.test_fiscal_api import FINANCE_PERMISSIONS, finance_headers
from tests.test_masters import post, prepare


async def test_charge_policy_editor_uses_current_native_controls(client: httpx.AsyncClient) -> None:
    await prepare(client)
    current = finance_headers(
        permissions=FINANCE_PERMISSIONS | {"accounting.charges.read", "accounting.charges.manage"}
    )
    path = f"/v1/companies/{COMPANY}/configuration/charge-policies/field-set"
    result = await client.get(path, params={"operation": "create"}, headers=current)
    assert result.status_code == 200, result.text
    fields = {field["key"]: field for field in result.json()["fields"]}
    assert fields["offset_account_id"]["control"]["reference"] == "accounts"
    assert fields["rate"]["control"]["kind"] == "decimal"
    assert fields["day_basis"]["control"]["choices"] == ["360", "365"]
    rates = await client.get(
        f"/v1/companies/{COMPANY}/configuration/withholding-rates/field-set", headers=current
    )
    bounds = next(
        field["control"]["decimal_bounds"]
        for field in rates.json()["fields"]
        if field["key"] == "rate_percent"
    )
    assert bounds == {"minimum": "0", "maximum": "100"}
    assert result.json()["lifecycle"] == "dates"
    assert (await client.get(path, headers=finance_headers())).status_code == 403


async def test_exchange_context_exposes_only_authorized_company_choices(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    path = f"/v1/companies/{COMPANY}/exchange-rates/context"
    result = await client.get(
        path,
        headers=finance_headers(features={"multi_currency"}, allowed_currencies={"USD", "EUR"}),
    )
    assert result.status_code == 200, result.text
    assert result.json() == {
        "company_id": str(COMPANY),
        "base_currency": "INR",
        "allowed_currencies": ["EUR", "USD"],
        "multi_currency": True,
    }
    assert (await client.get(path)).status_code == 401


async def test_quote_save_recovery_retains_one_native_candidate(client: httpx.AsyncClient) -> None:
    await prepare(client)
    path = f"/v1/companies/{COMPANY}/exchange-rates/candidates"
    current = finance_headers(features={"multi_currency"}) | {"Idempotency-Key": str(uuid7())}
    body = {
        "from_currency": "USD",
        "to_currency": "INR",
        "purpose": "ACCOUNTING",
        "effective_date": "2026-05-01",
        "rate": "83.123456789012",
        "source_kind": "MANUAL",
        "source_reference": "Reviewed treasury quotation",
    }
    created = await client.post(path, json=body, headers=current)
    assert created.status_code == 201, created.text
    assert created.headers["Location"] == "quotes/" + created.json()["id"]
    assert (
        await client.get(
            path.rsplit("/", 1)[0] + "/" + created.headers["Location"], headers=current
        )
    ).status_code == 200
    replay = await client.post(path, json=body, headers=current)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == created.json()["id"]
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["rate"] == "83.123456789012"
    different = await client.post(path, json=body | {"rate": "84.0"}, headers=current)
    assert different.status_code == 422, different.text
    assert different.json()["error"]["code"] == "idempotency_key_reused"


async def test_quote_review_recovery_retains_checker_and_one_version(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    maker, checker = uuid7(), uuid7()
    root = f"/v1/companies/{COMPANY}/exchange-rates"
    made = await client.post(
        root + "/candidates",
        json={
            "from_currency": "USD",
            "to_currency": "INR",
            "purpose": "ACCOUNTING",
            "effective_date": "2026-05-02",
            "rate": "83.123456789012",
            "source_kind": "MANUAL",
            "source_reference": "Reviewed treasury quote",
        },
        headers=finance_headers(user=maker, features={"multi_currency"}),
    )
    assert made.status_code == 201, made.text
    path = root + "/" + made.json()["id"] + "/approve"
    decision = {"expected_version": 1, "reason": "Independent source review"}
    assert (
        await client.post(
            path, json=decision, headers=finance_headers(user=maker, features={"multi_currency"})
        )
    ).status_code == 409
    current = finance_headers(user=checker, features={"multi_currency"})
    for _ in range(2):
        approved = await client.post(path, json=decision, headers=current)
        assert approved.status_code == 200, approved.text
        assert approved.json()["approved_by"] == str(checker)
        assert approved.json()["row_version"] == 2
    assert approved.headers["Idempotency-Replayed"] == "true"
    denied = await client.post(
        path,
        json=decision,
        headers=finance_headers(
            user=checker, permissions={"accounting.finance.read"}, features={"multi_currency"}
        )
        | {"Idempotency-Key": current["Idempotency-Key"]},
    )
    assert denied.status_code == 403


async def test_native_filter_hints_respect_field_authority(client: httpx.AsyncClient) -> None:
    await prepare(client)
    policy = {
        "entity_type": "accounting.account",
        "field_key": "party_id",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    result = await client.get(
        f"/v1/companies/{COMPANY}/configuration/accounts/field-set",
        headers=headers(policies=[policy]),
    )
    assert result.status_code == 200, result.text
    assert "party_id" not in result.json()["filter_keys"]
    assert "group_id" in result.json()["filter_keys"]
    assert result.json()["searchable"] is True


async def test_charge_offset_choices_exclude_multi_currency_accounts(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    root = f"/v1/companies/{COMPANY}"
    for mode in ("BASE", "MULTI"):
        await post(
            client,
            "/accounts",
            {
                "code": "MODE-" + mode,
                "name": "Mode " + mode,
                "kind": "GENERAL",
                "group_id": groups["INDIRECT_EXPENSES"],
                "currency_mode": mode,
            },
            h=finance_headers(features={"multi_currency"}),
        )
    result = await client.get(
        root + "/configuration/options/accounts",
        params={"q": "MODE", "kind": "GENERAL", "currency_mode": "BASE"},
        headers=finance_headers(),
    )
    assert result.status_code == 200, result.text
    assert [row["code"] for row in result.json()["items"]] == ["MODE-BASE"]
    assert (
        await client.get(
            root + "/configuration/options/currencies",
            headers=finance_headers(permissions={"accounting.charges.read"}),
        )
    ).status_code == 200
