"""Salespeople are company masters, not login identities or grants."""

from billing_platform.ids import uuid7


async def test_salesperson_master_is_optional_scoped_and_versioned(
    client, session, tenant_a, tenant_b
):
    from tests.api_support import actor_headers, grant
    from tests.factories import seed_two_companies

    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    actor_a = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(["company.update", "company.read"], scope_type="company", scope_id=company_a)
        ],
    )
    created = await client.post(
        f"/v1/companies/{company_a}/salespeople",
        headers=actor_a,
        json={"code": "FIELD_1", "name": "Field representative"},
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["user_id"] is None and item["row_version"] == 1
    listed = await client.get(f"/v1/companies/{company_a}/salespeople", headers=actor_a)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [item["id"]]
    stale = await client.patch(
        f"/v1/companies/{company_a}/salespeople/{item['id']}",
        headers=actor_a,
        json={"expected_version": 2, "is_active": False},
    )
    assert stale.status_code == 409
    updated = await client.patch(
        f"/v1/companies/{company_a}/salespeople/{item['id']}",
        headers=actor_a,
        json={"expected_version": 1, "is_active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["row_version"] == 2 and not updated.json()["is_active"]
    assert (
        await client.get(f"/v1/companies/{company_b}/salespeople/{item['id']}", headers=actor_a)
    ).status_code == 403
