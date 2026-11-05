"""Native editor/picker contracts preserve current fields, company scope and lifecycle."""

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.masters import AccountingSetup
from tests.conftest import COMPANY, TENANT, headers
from tests.test_masters import BASE, activate, new_party, party, post, prepare


async def test_configuration_controls_and_operation_rules(client: httpx.AsyncClient) -> None:
    await prepare(client)
    response = await client.get(
        BASE + "/configuration/accounts/field-set?operation=create", headers=headers()
    )
    assert response.status_code == 200, response.text
    form = response.json()
    fields = {field["key"]: field for field in form["fields"]}
    assert form["company_id"] == str(COMPANY)
    assert fields["kind"]["control"]["choices"] == [
        "GENERAL",
        "CASH",
        "BANK",
        "PARTY",
        "TAX",
        "INVENTORY_CONTROL",
        "ASSET_CONTROL",
    ]
    assert fields["rounding_limit"]["control"]["kind"] == "decimal"
    assert fields["group_id"]["control"]["reference"] == "account-groups"
    assert fields["currency"]["control"]["reference"] == "currencies"
    bank = await client.get(
        BASE + "/configuration/party-bank-accounts/field-set?operation=create", headers=headers()
    )
    number = next(field for field in bank.json()["fields"] if field["key"] == "account_number")
    assert number["control"]["write_only"] is True and number["editable"] is True
    assert (
        await client.get(
            BASE + "/configuration/accounts/field-set?operation=update", headers=headers()
        )
    ).status_code == 422
    assert (
        await client.get(
            BASE + f"/configuration/accounts/field-set?operation=create&object_id={uuid7()}",
            headers=headers(),
        )
    ).status_code == 422


async def test_account_editor_protects_active_semantics_and_identity(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    account = await post(
        client,
        "/accounts",
        {
            "code": "CONFIG",
            "name": "Configuration ledger",
            "group_id": groups["INDIRECT_EXPENSES"],
            "kind": "GENERAL",
        },
    )
    path = BASE + "/configuration/accounts/field-set?operation=update&object_id=" + account["id"]
    fresh = (await client.get(path, headers=headers())).json()
    assert next(field for field in fresh["fields"] if field["key"] == "code")["editable"] is False
    assert (
        next(field for field in fresh["fields"] if field["key"] == "group_id")["editable"] is True
    )
    policy = {
        "entity_type": "accounting.account",
        "field_key": "kind",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    hidden = (await client.get(path, headers=headers(policies=[policy]))).json()
    hidden_kind = next(field for field in hidden["fields"] if field["key"] == "kind")
    assert hidden_kind["editable"] is False
    assert "PARTY" in hidden_kind["control"]["choices"]
    await activate(client, "/accounts", account)
    active = (await client.get(path, headers=headers())).json()
    assert (
        next(field for field in active["fields"] if field["key"] == "group_id")["editable"] is False
    )
    assert next(field for field in active["fields"] if field["key"] == "name")["editable"] is True
    foreign = await client.get(path.replace(str(COMPANY), str(uuid7())), headers=headers())
    assert foreign.status_code in {401, 403}


async def test_configuration_reader_and_masked_fields(client: httpx.AsyncClient) -> None:
    await prepare(client)
    reader = headers(permissions={"accounting.party.read"})
    response = await client.get(
        BASE + "/configuration/parties/field-set?operation=create", headers=reader
    )
    assert response.status_code == 200
    assert response.json()["can_create"] is False
    assert not any(field["editable"] for field in response.json()["fields"])
    policy = {
        "entity_type": "accounting.party",
        "field_key": "legal_name",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    masked = await client.get(
        BASE
        + "/configuration/parties/field-set?operation=update&object_id="
        + (await party(client))["id"],
        headers=headers(policies=[policy]),
    )
    field = next(field for field in masked.json()["fields"] if field["key"] == "legal_name")
    assert field["readable"] is False and field["editable"] is False
    assert (
        await client.get(BASE + "/configuration/accounts/field-set", headers=reader)
    ).status_code == 403
    assert (await client.get(BASE + "/configuration/parties/field-set")).status_code == 401


async def test_supplier_filter_uses_active_role_without_duplicate_party_identity(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    supplier = await party(client)
    # A second party that holds a role, but not the supplier role: the filter must leave it out.
    other = await new_party(
        client, code="OTHER", role="CUSTOMER", name="Other party", legal_name="Other party"
    )
    result = await client.get(BASE + "/parties?role=SUPPLIER", headers=headers())
    assert result.status_code == 200, result.text
    assert [row["id"] for row in result.json()["items"]] == [supplier["id"]]
    roles = await client.get(
        BASE + "/party-roles?role=SUPPLIER&party_id=" + supplier["id"], headers=headers()
    )
    assert len(roles.json()["items"]) == 1
    assert other["id"] != supplier["id"]
    policy = {
        "entity_type": "accounting.party_role",
        "field_key": "role",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    assert (
        await client.get(BASE + "/parties?role=SUPPLIER", headers=headers(policies=[policy]))
    ).status_code == 403


async def test_configuration_choices_exact_hydration_search_and_signed_paging(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    path = BASE + "/configuration/options/account-groups"
    first = await client.get(path + "?limit=1", headers=headers())
    assert first.status_code == 200, first.text
    body = first.json()
    assert len(body["items"]) == 1 and body["page"]["has_more"] is True
    cursor = body["page"]["next_cursor"]
    next_page = await client.get(path, params={"limit": 1, "cursor": cursor}, headers=headers())
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["value"] != body["items"][0]["value"]
    exact = await client.get(path, params={"value": body["items"][0]["value"]}, headers=headers())
    assert exact.json()["items"] == body["items"]
    search = await client.get(path, params={"q": "Sales"}, headers=headers())
    assert search.status_code == 200 and search.json()["items"]
    assert (
        await client.get(
            path, params={"limit": 1, "cursor": cursor, "q": "Sales"}, headers=headers()
        )
    ).status_code in {409, 422}


async def test_picker_admission_and_unsupported_filters(client: httpx.AsyncClient) -> None:
    await prepare(client)
    path = BASE + "/configuration/options/account-groups"
    assert (await client.get(path)).status_code == 401
    assert (
        await client.get(path, headers=headers(permissions={"accounting.party.read"}))
    ).status_code == 403
    assert (await client.get(path + "?value=invalid", headers=headers())).status_code == 422
    assert (
        await client.get(path + "?party_id=" + str(uuid7()), headers=headers())
    ).status_code == 422
    assert (
        await client.get(BASE + "/configuration/options/states", headers=headers())
    ).status_code == 422
    assert (await client.get(path + "?limit=1&limit=2", headers=headers())).status_code == 422
    policy = {
        "entity_type": "accounting.account_group",
        "field_key": "name",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    assert (await client.get(path, headers=headers(policies=[policy]))).status_code == 403


async def test_editor_hints_do_not_disclose_protected_lifecycle(client: httpx.AsyncClient) -> None:
    await prepare(client)
    account = (await client.get(BASE + "/accounts?limit=1", headers=headers())).json()["items"][0]
    for key in ("status", "used_at", "system_key"):
        policy = {
            "entity_type": "accounting.account",
            "field_key": key,
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
            "condition": None,
        }
        response = await client.get(
            BASE + "/configuration/accounts/field-set?operation=update&object_id=" + account["id"],
            headers=headers(policies=[policy]),
        )
        assert response.status_code == 403, key


async def test_withholding_rate_references_have_distinct_readable_terms(
    client: httpx.AsyncClient,
) -> None:
    from tests.test_withholding_api import h, rate_body, send, world

    configured = await world(client)
    rate = await send(client, "/withholding-rates", rate_body(configured["section"]))
    result = await client.get(BASE + "/configuration/options/withholding-rates", headers=h())
    assert result.status_code == 200, result.text
    option = next(row for row in result.json()["items"] if row["value"] == rate["id"])
    assert "COMPANY" in option["label"] and rate["valid_from"] in option["label"]


async def test_reference_denial_precedes_company_setup_readiness(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            setup = await db.scalar(
                select(AccountingSetup).where(AccountingSetup.company_id == COMPANY)
            )
            assert setup is not None
            setup.metadata_version = 0
    result = await client.get(
        BASE + "/configuration/options/account-groups",
        headers=headers(permissions={"accounting.party.read"}),
    )
    assert result.status_code == 403
    form_result = await client.get(
        BASE + "/configuration/accounts/field-set",
        headers=headers(permissions={"accounting.party.read"}),
    )
    assert form_result.status_code == 403


async def retire_role(client: httpx.AsyncClient, party_id: str, role: str) -> httpx.Response:
    """Retire a party role as the rules require: its account first, then the role itself.

    Every role now has a live account, and a role cannot be retired while its account is live.
    """
    page = await client.get(BASE + "/accounts", params={"party_id": party_id}, headers=headers())
    for account in page.json()["items"]:
        if account["party_role"] == role and account["status"] == "ACTIVE":
            await post(
                client,
                "/accounts/" + account["id"] + "/deactivate",
                {"expected_version": account["row_version"]},
                status=200,
            )
    found = await client.get(
        BASE + "/party-roles", params={"party_id": party_id, "role": role}, headers=headers()
    )
    row = found.json()["items"][0]
    return await client.post(
        BASE + "/party-roles/" + row["id"] + "/deactivate",
        json={"expected_version": row["row_version"]},
        headers=headers() | {"Idempotency-Key": str(uuid7())},
    )


async def test_party_reference_choices_use_active_roles_and_retain_exact_history(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    owner = await party(client)
    # A party is never created without a role any more, so "no active role" is a retired one.
    other = await new_party(
        client,
        code="NO_ROLE",
        role="CUSTOMER",
        name="No active role",
        legal_name="No active role",
    )
    emptied = await retire_role(client, other["id"], "CUSTOMER")
    assert emptied.status_code == 200, emptied.text
    path = BASE + "/configuration/options/parties"
    for role in ("CUSTOMER", "SUPPLIER"):
        choices = await client.get(
            path, params={"status": "ACTIVE", "role": role}, headers=headers()
        )
        assert choices.status_code == 200, choices.text
        assert [row["value"] for row in choices.json()["items"]] == [owner["id"]]
    retired = await retire_role(client, owner["id"], "SUPPLIER")
    assert retired.status_code == 200, retired.text
    choices = await client.get(
        path, params={"status": "ACTIVE", "role": "SUPPLIER"}, headers=headers()
    )
    assert choices.json()["items"] == []
    retained = await client.get(
        path,
        params={"value": owner["id"], "role": "SUPPLIER", "status": "ACTIVE"},
        headers=headers(),
    )
    assert retained.status_code == 200, retained.text
    assert [row["value"] for row in retained.json()["items"]] == [owner["id"]]
    for field in ("party_id", "role", "status"):
        policy = {
            "entity_type": "accounting.party_role",
            "field_key": field,
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
            "condition": None,
        }
        protected = await client.get(
            path, params={"role": "CUSTOMER"}, headers=headers(policies=[policy])
        )
        assert protected.status_code == 403, protected.text
    assert (await client.get(path, params={"role": "CUSTOMER"})).status_code == 401
    assert (
        await client.get(
            path.replace(str(COMPANY), str(uuid7())), params={"role": "CUSTOMER"}, headers=headers()
        )
    ).status_code in {401, 403}


async def test_master_free_text_preserves_multiline_notes_and_descriptions(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    notes = "First line\nSecond line"
    owner = await new_party(
        client, code="NOTES", name="Notes review", legal_name="Notes review", notes=notes
    )
    assert owner["notes"] == notes
    ledger = await post(
        client,
        "/accounts",
        {
            "code": "DESCRIPTION",
            "name": "Description review",
            "group_id": groups["INDIRECT_EXPENSES"],
            "description": notes,
        },
    )
    assert ledger["description"] == notes
