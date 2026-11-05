from __future__ import annotations

from tests.api_support import actor_headers, grant
from tests.factories import seed_two_companies
from tests.test_api_company_statutory import _gst_body, _headers


async def test_tax_registration_lookup_matches_number_and_saved_id_without_cross_company_access(
    client, session, tenant_a, tenant_b
):
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    path = f"/v1/companies/{company}/tax-registrations"
    added = await client.post(
        path, json=_gst_body(), headers=_headers(tenant_a, ["company.tax_registration.manage"])
    )
    assert added.status_code == 201, added.text
    headers = _headers(tenant_a, ["company.read"])
    match = await client.get(path + "?q=27AA", headers=headers)
    assert match.status_code == 200, match.text
    assert len(match.json()["items"]) == 1
    assert (await client.get(path + "?q=99", headers=headers)).json()["items"] == []
    record_id = added.json()["id"]
    selected = await client.get(path + "?id=" + record_id, headers=headers)
    assert selected.status_code == 200
    assert selected.json()["items"][0]["id"] == record_id
    assert (await client.get(path + "?q=2", headers=headers)).status_code == 422
    assert (await client.get(path + "?id=wrong", headers=headers)).status_code == 422
    scoped = actor_headers(
        tenant_id=tenant_a,
        user_id=company,
        grants=[grant(["company.read"], scope_type="company", scope_id=company)],
    )
    denied = await client.get(
        f"/v1/companies/{other}/tax-registrations?id={record_id}", headers=scoped
    )
    assert denied.status_code in {403, 404}
