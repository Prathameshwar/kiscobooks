import datetime as dt
from typing import Any, cast

import httpx

from tests.conftest import COMPANY, headers
from tests.test_masters import BASE, new_party, party, post, prepare


async def party_account(client: httpx.AsyncClient, party_id: str, role: str) -> dict[str, Any]:
    """The party's account for a role, in full: the list projection carries no `party_role`."""
    listed = (await client.get(BASE + "/accounts?kind=PARTY&limit=200", headers=headers())).json()
    for item in listed["items"]:
        if item["party_id"] != party_id:
            continue
        detail = await client.get(f'{BASE}/accounts/{item["id"]}', headers=headers())
        assert detail.status_code == 200, detail.text
        if detail.json()["party_role"] == role:
            return cast(dict[str, Any], detail.json())
    raise AssertionError(f"party {party_id} has no account for {role}")


async def retire_account(client: httpx.AsyncClient, party_id: str, role: str) -> None:
    """Deactivate a party's account for a role.

    Every active role now holds a live account, and a live account is the first thing that blocks
    the role's retirement. A test of any later retirement guard retires the account first so the
    guard under test is the only one left standing.
    """
    account = await party_account(client, party_id, role)
    retired = await post(
        client,
        f'/accounts/{account["id"]}/deactivate',
        {"expected_version": account["row_version"]},
        status=200,
    )
    assert retired["status"] == "INACTIVE"


async def seeded_account(client: httpx.AsyncClient, system_key: str) -> dict[str, Any]:
    """Template accounts are addressed by system key; their codes are template content."""
    items = (await client.get(BASE + "/accounts", headers=headers())).json()["items"]
    return cast(dict[str, Any], next(row for row in items if row["system_key"] == system_key))


async def roles_of(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    items = (await client.get(BASE + "/party-roles", headers=headers())).json()["items"]
    return {row["role"]: row for row in items}


async def roles_for(client: httpx.AsyncClient, party_id: str) -> set[tuple[str, str]]:
    items = (await client.get(BASE + "/party-roles?limit=200", headers=headers())).json()["items"]
    return {(row["role"], row["status"]) for row in items if row["party_id"] == party_id}


async def party_accounts_of(client: httpx.AsyncClient, party_id: str) -> list[dict[str, Any]]:
    items = (await client.get(BASE + "/accounts?kind=PARTY&limit=200", headers=headers())).json()
    return [row for row in items["items"] if row["party_id"] == party_id]


async def test_import_preview_rollback_apply_replay_and_stale(client: httpx.AsyncClient) -> None:
    await prepare(client)
    # A party arrives only with its role and account, so the import adds a second role to one
    # (a draft role, then its activation through a staged reference) instead of creating it.
    imported = await new_party(
        client,
        code="IMPORT",
        role="CUSTOMER",
        name="Imported",
        legal_name="Imported Trading Limited",
    )
    body: dict[str, Any] = {
        "items": [
            {
                "key": "role",
                "resource": "party-roles",
                "values": {"party_id": imported["id"], "role": "SUPPLIER"},
            },
            {
                "key": "live",
                "resource": "party-roles",
                "action": "activate",
                "object_id": "$role",
                "values": {"expected_version": 1},
            },
        ]
    }
    preview = await post(client, "/imports/preview", body, status=200)
    assert preview["valid"], preview
    # The preview rolls back: neither the role nor its account exists afterwards.
    assert await roles_for(client, imported["id"]) == {("CUSTOMER", "ACTIVE")}
    assert len(await party_accounts_of(client, imported["id"])) == 1
    apply = body | {"preview_token": preview["preview_token"]}
    h = headers()
    applied = await post(client, "/imports/apply", apply, h=h, status=200)
    assert set(applied["records"]) == {"role", "live"}
    assert await post(client, "/imports/apply", apply, h=h, status=200) == applied
    assert await roles_for(client, imported["id"]) == {
        ("CUSTOMER", "ACTIVE"),
        ("SUPPLIER", "ACTIVE"),
    }
    assert len(await party_accounts_of(client, imported["id"])) == 2  # one replay, one account
    body["items"][0]["values"]["role"] = "OTHER"
    preview = await post(client, "/imports/preview", body, status=200)
    # Another master changes after the preview: a party now always arrives with role and account.
    await new_party(
        client, code="OTHER", role="CUSTOMER", name="Other", legal_name="Other Trading Limited"
    )
    result = await client.post(
        BASE + "/imports/apply",
        json=body | {"preview_token": preview["preview_token"]},
        headers=headers(),
    )
    assert result.status_code == 409
    body["items"][1]["object_id"] = "$missing"
    preview = await post(client, "/imports/preview", body, status=200)
    assert not preview["valid"] and preview["preview_token"] is None
    assert len((await client.get(BASE + "/parties", headers=headers())).json()["items"]) == 2
    # The refused and the invalid imports left the imported party exactly as the first apply did.
    assert await roles_for(client, imported["id"]) == {
        ("CUSTOMER", "ACTIVE"),
        ("SUPPLIER", "ACTIVE"),
    }
    assert len(await party_accounts_of(client, imported["id"])) == 2


async def test_the_generic_import_cannot_create_a_party_and_changes_nothing_with_it(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    await new_party(client, code="HAVE", role="CUSTOMER")
    terms = {"key": "t", "resource": "payment-terms", "values": {"code": "N30", "name": "Net 30"}}
    bare = {
        "key": "p",
        "resource": "parties",
        "values": {
            "code": "BARE",
            "name": "Bare",
            "legal_name": "Bare Trading Limited",
            "country_code": "IN",
        },
    }
    # A party row alone, or inside an otherwise valid batch, is a conflict issue: a party only
    # arrives with its role and ledger account (create-with-details or the ready import).
    for items in ([bare], [terms, bare]):
        preview = await post(client, "/imports/preview", {"items": items}, status=200)
        assert not preview["valid"] and preview["preview_token"] is None
        assert preview["issues"] == [{"key": "p", "code": "conflict"}]
    # A token earned by a valid preview of something else cannot carry the party row in.
    earned = await post(client, "/imports/preview", {"items": [terms]}, status=200)
    refused = await client.post(
        BASE + "/imports/apply",
        json={"items": [terms, bare], "preview_token": earned["preview_token"]},
        headers=headers(),
    )
    assert refused.status_code == 409, refused.text
    parties = (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    assert [row["code"] for row in parties] == ["HAVE"]
    assert (await client.get(BASE + "/payment-terms", headers=headers())).json()["items"] == []


async def test_activating_roles_through_the_generic_import_gives_them_their_account(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    supplier = await new_party(client, code="ABC", role="SUPPLIER")
    assert [row["code"] for row in await party_accounts_of(client, supplier["id"])] == ["ABC"]
    # BROKER and OTHER share the OTHER account role: the first activation creates the account,
    # the second reuses it, so the party still holds exactly one account per account role.
    items: list[dict[str, Any]] = []
    for role in ("BROKER", "OTHER"):
        items.append(
            {
                "key": role.lower(),
                "resource": "party-roles",
                "values": {"party_id": supplier["id"], "role": role},
            }
        )
        items.append(
            {
                "key": role.lower() + "_on",
                "resource": "party-roles",
                "action": "activate",
                "object_id": "$" + role.lower(),
                "values": {"expected_version": 1},
            }
        )
    preview = await post(client, "/imports/preview", {"items": items}, status=200)
    assert preview["valid"], preview
    assert len(await party_accounts_of(client, supplier["id"])) == 1  # nothing before the apply
    applied = await post(
        client,
        "/imports/apply",
        {"items": items, "preview_token": preview["preview_token"]},
        status=200,
    )
    assert len(applied["records"]) == 4
    assert await roles_for(client, supplier["id"]) == {
        ("SUPPLIER", "ACTIVE"),
        ("BROKER", "ACTIVE"),
        ("OTHER", "ACTIVE"),
    }
    shared = await party_account(client, supplier["id"], "OTHER")
    assert (shared["code"], shared["status"]) == ("ABC-OTHR", "ACTIVE")
    assert sorted(row["code"] for row in await party_accounts_of(client, supplier["id"])) == [
        "ABC",
        "ABC-OTHR",
    ]


async def test_mapping_review_publish_and_export_history(client: httpx.AsyncClient) -> None:
    await prepare(client)
    cash = await seeded_account(client, "account.CASH_MAIN")
    values: dict[str, Any] = {
        "purpose": "CASH_RECEIPT",
        "account_id": cash["id"],
        "currency": "INR",
        "valid_from": (dt.date.today() + dt.timedelta(days=1)).isoformat(),
    }
    row = await post(client, "/posting-mapping-drafts", {"values": values})
    await post(client, f'/posting-mapping-drafts/{row["id"]}/validate', {}, status=200)
    result = await client.post(
        BASE + f'/posting-mapping-drafts/{row["id"]}/publish',
        json={"expected_version": 1},
        headers=headers(permissions={"accounting.mapping.read", "accounting.mapping.manage"}),
    )
    assert result.status_code == 403
    h = headers()
    publish = f'/posting-mapping-drafts/{row["id"]}/publish'
    published = await post(client, publish, {"expected_version": 1}, h=h, status=200)
    assert published["published_mapping_id"]
    replay = await post(client, publish, {"expected_version": 1}, h=h, status=200)
    assert replay == published
    result = await client.patch(
        BASE + f'/posting-mapping-drafts/{row["id"]}',
        json={"expected_version": 2, "values": values},
        headers=headers(),
    )
    assert result.status_code == 409
    abc = await party(client)
    policy: dict[str, Any] = {
        "entity_type": "accounting.party",
        "field_key": "legal_name",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    result = await client.get(BASE + "/exports/parties", headers=headers(policies=[policy]))
    assert result.status_code == 200 and "legal_name" not in result.json()["items"][0]
    history = await client.get(BASE + f'/history/parties/{abc["id"]}', headers=headers())
    assert history.status_code == 200, history.text
    assert len(history.json()["items"]) == 2


async def test_role_retirement_and_direct_mapping_publish_permission(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    abc = await party(client)
    # The customer role came with its own account, and that live account blocks its retirement.
    assert (await party_account(client, abc["id"], "CUSTOMER"))["status"] == "ACTIVE"
    customer = (await roles_of(client))["CUSTOMER"]
    result = await client.post(
        BASE + f'/party-roles/{customer["id"]}/deactivate',
        json={"expected_version": customer["row_version"]},
        headers=headers(),
    )
    assert result.status_code == 409, result.text
    cash = await seeded_account(client, "account.CASH_MAIN")
    result = await client.post(
        BASE + "/posting-mappings",
        json={
            "purpose": "CASH_RECEIPT",
            "account_id": cash["id"],
            "currency": "INR",
            "valid_from": (dt.date.today() + dt.timedelta(days=1)).isoformat(),
        },
        headers=headers(permissions={"accounting.mapping.manage", "accounting.mapping.read"}),
    )
    assert result.status_code == 403


async def test_role_retirement_guards_value_scoped_policies(client: httpx.AsyncClient) -> None:
    """A role-scoped policy names its role by value, so the generic reference walk misses it."""
    await prepare(client)
    abc = await party(client)
    # Each role holds a live account, which blocks retirement first; retire both accounts so the
    # guard under test (the role-scoped policy, which names its role by value) stands alone.
    await retire_account(client, abc["id"], "CUSTOMER")
    await retire_account(client, abc["id"], "SUPPLIER")
    roles = await roles_of(client)
    await post(
        client,
        "/party-credit-policies",
        {
            "party_id": abc["id"],
            "limit_amount": "50000.0000",
            "currency": "INR",
            "valid_from": (dt.date.today() + dt.timedelta(days=1)).isoformat(),
        },
    )
    blocked = await client.post(
        BASE + f'/party-roles/{roles["CUSTOMER"]["id"]}/deactivate',
        json={"expected_version": roles["CUSTOMER"]["row_version"]},
        headers=headers(),
    )
    assert blocked.status_code == 409, blocked.text
    # SUPPLIER's account is retired and it carries no policy, so the guard must let it retire.
    await post(
        client,
        f'/party-roles/{roles["SUPPLIER"]["id"]}/deactivate',
        {"expected_version": roles["SUPPLIER"]["row_version"]},
        status=200,
    )
