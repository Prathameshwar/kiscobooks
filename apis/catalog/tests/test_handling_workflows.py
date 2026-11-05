import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.test_commercial_api import command_headers
from tests.test_handling_api import setup_profile


async def test_handling_exact_bounds_lifecycle_publication_and_lists(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, current, master = await setup_profile(client, factory, tenant_a)
    route, revisions = master.rsplit("/", 1)[0], master + "/revisions"
    renamed = await client.patch(
        master, headers=command_headers(current), json={"expected_version": 1, "code": "CHILLED"}
    )
    assert renamed.status_code == 200
    payload: dict[str, Any] = {
        "temperature_min": "2.1234",
        "temperature_max": "8",
        "temperature_unit": "CELSIUS",
        "keep_upright": True,
        "instructions": "  Protect\nKeep dry  ",
    }
    receipt = command_headers(current)
    draft = await client.post(revisions, headers=receipt, json=payload)
    assert draft.status_code == 201, draft.text
    assert (
        draft.json()["temperature_min"] == "2.1234" and draft.json()["temperature_max"] == "8.0000"
    )
    assert draft.json()["instructions"] == "Protect\nKeep dry"
    assert (await client.post(revisions, headers=receipt, json=payload)).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = revisions + "/" + draft.json()["id"]
    assert (await client.get(detail, headers=current)).json()["temperature_unit"] == "CELSIUS"
    assert (
        await client.patch(
            master, headers=command_headers(current), json={"expected_version": 2, "code": "OTHER"}
        )
    ).status_code == 409
    assert (
        await client.patch(
            master,
            headers=command_headers(current),
            json={"expected_version": 2, "name": "Cold storage"},
        )
    ).status_code == 200
    for invalid in (
        {"temperature_min": "2"},
        {"temperature_unit": "CELSIUS"},
        {"fragile": "false"},
        {**payload, "temperature_unit": "FAHRENHEIT"},
        {**payload, "temperature_min": 2.1},
        {**payload, "temperature_min": "2.12345"},
        {**payload, "temperature_min": "NaN"},
        {**payload, "temperature_min": "-273.1501"},
        {**payload, "temperature_max": "1"},
        {**payload, "instructions": "   "},
        {**payload, "instructions": "bad\x00text"},
        {**payload, "hazardous_material_permit": "unknown"},
    ):
        assert (
            await client.post(revisions, headers=command_headers(current), json=invalid)
        ).status_code == 422
    for field in ("fragile", "keep_dry", "keep_upright"):
        assert (
            await client.patch(
                detail, headers=command_headers(current), json={"expected_version": 1, field: None}
            )
        ).status_code == 422
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 1, "temperature_max": "1"},
        )
    ).status_code == 422
    noop = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, "temperature_max": "8.0000"},
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 1
    changed = await client.patch(
        detail,
        headers=command_headers(current),
        json={
            "expected_version": 1,
            "temperature_min": "-273.15",
            "instructions": None,
            "fragile": True,
        },
    )
    assert (
        changed.status_code == 200
        and changed.json()["row_version"] == 2
        and changed.json()["instructions"] is None
    )
    publication = command_headers(current)
    assert (
        await client.post(detail + "/publish", headers=publication, json={"expected_version": 2})
    ).status_code == 200
    assert (
        await client.post(detail + "/publish", headers=publication, json={"expected_version": 2})
    ).headers["Idempotency-Replayed"] == "true"
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 3, "temperature_min": "3"},
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 3}
        )
    ).status_code == 409
    second = await client.post(revisions, headers=command_headers(current), json={})
    assert second.status_code == 201 and second.json()["revision"] == 2
    second_path = revisions + "/" + second.json()["id"]
    measured = await client.patch(
        second_path,
        headers=command_headers(current),
        json={"expected_version": 1, "temperature_max": "8", "temperature_unit": "CELSIUS"},
    )
    assert measured.status_code == 200
    cleared = await client.patch(
        second_path,
        headers=command_headers(current),
        json={"expected_version": 2, "temperature_max": None, "temperature_unit": None},
    )
    assert cleared.status_code == 200 and cleared.json()["temperature_unit"] is None
    page = await client.get(revisions, headers=current, params={"limit": 1, "sort": "-revision"})
    assert (
        page.status_code == 200
        and "instructions" not in page.json()["items"][0]
        and "temperature_min" not in page.json()["items"][0]
    )
    following = await client.get(
        revisions,
        headers=current,
        params={"limit": 1, "sort": "-revision", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert following.json()["items"][0]["id"] == draft.json()["id"]
    for query in (
        {"published": "true"},
        {"fragile": "true", "keep_dry": "false", "keep_upright": "true"},
    ):
        filtered = await client.get(revisions, headers=current, params=query)
        assert filtered.status_code == 200 and len(filtered.json()["items"]) == 1
    for query in ({"q": "cold"}, {"sort": "temperature_max"}):
        assert (await client.get(revisions, headers=current, params=query)).status_code == 422
    assert (await client.get(route, headers=current, params={"q": "Cold", "sort": "name"})).json()[
        "items"
    ][0]["id"] == master.rsplit("/", 1)[-1]
    for action, version in (("deactivate", 3), ("activate", 4)):
        assert (
            await client.post(
                master + "/" + action,
                headers=command_headers(current),
                json={"expected_version": version},
            )
        ).status_code == 200
        if action == "deactivate":
            assert (
                await client.post(revisions, headers=command_headers(current), json={})
            ).status_code == 409
            assert (
                await client.patch(
                    second_path, headers=command_headers(current), json={"expected_version": 3}
                )
            ).status_code == 409
    options = await client.get(
        f"/v1/companies/{company}/option-sources/catalog.handling_profiles", headers=current
    )
    assert options.status_code == 200 and options.json()["items"][0]["code"] == "CHILLED"
