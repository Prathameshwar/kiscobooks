from tests.test_api_tax_registration_rules import MANAGE, _create, world  # noqa: F401
from tests.test_gst_filing_api import engine  # noqa: F401


async def test_profile_native_money_scope_history_and_close(client, world):  # noqa: F811
    setup = await client.get(
        f"/v1/companies/{world.company}/gst-outward-profile-setup",
        headers=world.headers("company.read"),
    )
    assert setup.status_code == 200, setup.text
    assert setup.json()["can_manage"] is False
    assert "annual_turnover" in setup.json()["create_schema"]["properties"]
    registration = await _create(client, world)
    path = f"/v1/companies/{world.company}/gst-outward-profiles"
    body = {
        "registration_id": registration["id"],
        "annual_turnover": "50000000.0001",
        "rule_14a": False,
        "valid_from": "2026-04-01",
        "reference": "Reviewed preceding-year PAN turnover",
        "evidence_hash": "a" * 64,
    }
    result = await client.post(path, headers=world.headers(MANAGE), json=body)
    assert result.status_code == 201, result.text
    assert result.json()["annual_turnover"] == "50000000.0001"
    assert (await client.post(path, headers=world.headers(MANAGE), json=body)).status_code == 409
    assert (
        await client.post(path, headers=world.headers("company.read"), json=body)
    ).status_code == 403
    assert (
        await client.post(path, headers=world.headers(MANAGE), json=body | {"annual_turnover": 1.2})
    ).status_code == 422
    assert (await client.get(path, headers=world.headers("company.read"))).status_code == 200
    assert (
        await client.get(
            f"/v1/companies/{world.other_company}/gst-outward-profiles",
            headers=world.headers("company.read", company=world.company),
        )
    ).status_code == 403
    closed = await client.patch(
        path + "/" + result.json()["id"],
        headers=world.headers(MANAGE),
        json={"valid_to": "2027-04-01"},
    )
    assert closed.status_code == 200, closed.text
    assert (
        await client.patch(
            path + "/" + result.json()["id"],
            headers=world.headers(MANAGE),
            json={"valid_to": "2027-05-01"},
        )
    ).status_code == 409
