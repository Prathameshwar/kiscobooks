"""Party identity types and active roles are lean, independently protected list data."""

import httpx

from tests.conftest import headers
from tests.test_masters import BASE, new_party, party, party_accounts, post, prepare


async def test_party_list_types_roles_paging_and_field_protection(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    organisation = await party(client)
    # A party always has an active role (and its account): an individual comes in as "other".
    person = await new_party(
        client,
        code="PERSON",
        role="OTHER",
        name="Individual party",
        legal_name="Individual party",
        party_type="PERSON",
    )
    await post(client, "/party-roles", {"party_id": organisation["id"], "role": "BROKER"})
    result = await client.get(BASE + "/parties", headers=headers())
    assert result.status_code == 200, result.text
    rows = {row["id"]: row for row in result.json()["items"]}
    assert rows[organisation["id"]]["party_type"] == "ORGANISATION"
    assert rows[organisation["id"]]["roles"] == ["CUSTOMER", "SUPPLIER"]
    assert rows[person["id"]]["party_type"] == "PERSON"
    assert rows[person["id"]]["roles"] == ["OTHER"]
    assert "legal_name" not in rows[organisation["id"]]

    first = await client.get(BASE + "/parties?limit=1", headers=headers())
    assert first.status_code == 200, first.text
    second = await client.get(
        BASE + "/parties",
        headers=headers(),
        params={
            "limit": 1,
            "cursor": first.json()["page"]["next_cursor"],
        },
    )
    assert second.status_code == 200, second.text
    paged = first.json()["items"] + second.json()["items"]
    assert {row["id"] for row in paged} == set(rows)
    assert all(row["roles"] == rows[row["id"]]["roles"] for row in paged)

    for entity, field, hidden in [
        ("party", "party_type", "party_type"),
        ("party_role", "party_id", "roles"),
        ("party_role", "role", "roles"),
        ("party_role", "status", "roles"),
    ]:
        protected = await client.get(
            BASE + "/parties",
            headers=headers(
                policies=[
                    {
                        "entity_type": "accounting." + entity,
                        "field_key": field,
                        "access": "read",
                        "effect": "deny",
                        "scope_type": "company",
                        "scope_id": organisation["company_id"],
                    }
                ]
            ),
        )
        assert protected.status_code == 200, protected.text
        assert all(hidden not in row for row in protected.json()["items"])

    roles = await client.get(BASE + "/party-roles", headers=headers())
    assert roles.status_code == 200, roles.text
    assert any(row["role"] == "BROKER" for row in roles.json()["items"])
    supplier = next(row for row in roles.json()["items"] if row["role"] == "SUPPLIER")
    # A role cannot be retired while its account is live: the account goes first.
    refused = await client.post(
        BASE + "/party-roles/" + supplier["id"] + "/deactivate",
        json={"expected_version": supplier["row_version"]},
        headers=headers(),
    )
    assert refused.status_code == 409, refused.text
    ledger = next(
        row
        for row in await party_accounts(client, organisation["id"])
        if row["party_role"] == "SUPPLIER"
    )
    await post(
        client,
        "/accounts/" + ledger["id"] + "/deactivate",
        {"expected_version": ledger["row_version"]},
        status=200,
    )
    await post(
        client,
        "/party-roles/" + supplier["id"] + "/deactivate",
        {
            "expected_version": supplier["row_version"],
        },
        status=200,
    )
    result = await client.get(BASE + "/parties", headers=headers(), params={"code": "ABC"})
    assert result.status_code == 200, result.text
    assert result.json()["items"][0]["roles"] == ["CUSTOMER"]
