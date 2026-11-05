"""Serial identity preflight preserves native scope and field authority."""

from billing_platform.ids import uuid7

from accounting.api import stock_tracking as api
from tests.conftest import COMPANY, headers
from tests.test_masters import prepare
from tests.test_stock_tracking import BASE, auth, create_batch, facts, serial


async def test_serial_collision_check_uses_native_company_identity_and_read_authority(
    client, monkeypatch
):
    async def source(request, current, item, **kwargs):
        return facts(current.context.company_id, item)

    monkeypatch.setattr(api, "source", source)
    await prepare(client)
    batch = await create_batch(client)
    created = await client.post(BASE + "/serials", headers=auth(), json=serial(batch["id"], "ABC"))
    assert created.status_code == 201, created.text
    path = BASE + "/serials/check-identifiers"
    body = {"identifiers": [{"identifier_type": "SERIAL", "value": "ＡＢＣ"}]}  # noqa: RUF001
    duplicate = await client.post(path, headers=auth(), json=body)
    assert duplicate.status_code == 422, duplicate.text
    assert "identifiers.0.value" in duplicate.json()["error"]["fields"]
    available = await client.post(
        path, headers=auth(), json={"identifiers": [{"identifier_type": "SERIAL", "value": "DEF"}]}
    )
    assert available.status_code == 200 and available.json()["available"] is True
    assert (await client.post(path, json=body)).status_code == 401
    assert (await client.post(path, headers=headers(), json=body)).status_code == 403
    assert (
        await client.post(path.replace(str(COMPANY), str(uuid7())), headers=auth(), json=body)
    ).status_code in {401, 403}
    denied = await client.post(
        path,
        headers=auth(
            policies=[
                {
                    "entity_type": "accounting.stock_unit",
                    "field_key": "identifiers",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        ),
        json=body,
    )
    assert denied.status_code == 403, denied.text
