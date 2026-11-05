"""Every exported master is typed, sparse and usable through stable workflow contracts."""

from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI

from accounting.resources import RESOURCES
from tests.conftest import COMPANY, headers
from tests.test_masters import BASE, post, prepare


async def test_every_typed_export_enforces_its_scope_and_response_contract(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    for spec in RESOURCES:
        url = BASE + "/exports/" + spec.path
        result = await client.get(url, headers=headers())
        assert result.status_code == 200, (spec.name, result.text)
        assert result.headers["cache-control"] == "no-store"
        for row in result.json()["items"]:
            spec.detail.model_validate(row)
            assert row["company_id"] == str(COMPANY)
            assert "account_number" not in row and "account_number_ciphertext" not in row
        denied = await client.get(url, headers=headers(permissions={"accounting.export.read"}))
        assert denied.status_code == 403, (spec.name, denied.text)
        invalid = await client.get(url + "?unknown=1", headers=headers())
        assert invalid.status_code == 422, (spec.name, invalid.text)


def test_exports_have_individual_openapi_contracts(app: FastAPI) -> None:
    schema = app.openapi()
    for spec in RESOURCES:
        operation = schema["paths"]["/v1/companies/{company_id}/exports/" + spec.path]["get"]
        page_name = operation["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ].split("/")[-1]
        item = schema["components"]["schemas"][page_name]["properties"]["items"]["items"]
        assert item["$ref"].endswith("/" + spec.detail.__name__)
    assert "/v1/companies/{company_id}/exports/{resource}" not in schema["paths"]


def test_decimal_input_contract_does_not_offer_float_values(app: FastAPI) -> None:
    field = app.openapi()["components"]["schemas"]["AccountCreate"]["properties"]["rounding_limit"]
    options = field.get("anyOf", [field])
    assert {option.get("type") for option in options} == {"string", "null"}


async def test_create_and_replay_return_a_resolvable_location(client: httpx.AsyncClient) -> None:
    await prepare(client)
    body: dict[str, Any] = {
        "code": "LOC",
        "name": "Location",
        "legal_name": "Location",
        "country_code": "IN",
        "role": "SUPPLIER",
    }
    h = headers()
    first = await client.post(BASE + "/parties/create-with-details", json=body, headers=h)
    assert first.status_code == 201, first.text
    assert first.headers.get("location")
    location = urljoin(str(first.request.url), first.headers["location"])
    # The create command is a collection action; its location is the party it created.
    collection = str(first.request.url).removesuffix("/create-with-details")
    assert location == collection + "/" + first.json()["id"]
    assert (await client.get(location, headers=headers())).status_code == 200
    repeat = await client.post(BASE + "/parties/create-with-details", json=body, headers=h)
    assert repeat.headers["location"] == first.headers["location"]
    assert repeat.json() == first.json()


async def test_group_alias_import_export_history_and_field_policy(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    body: dict[str, Any] = {
        "items": [
            {
                "key": "alias",
                "resource": "account-group-aliases",
                "values": {"group_id": groups["SALES"], "alias": "Revenue alias"},
            }
        ]
    }
    preview = await post(client, "/imports/preview", body, status=200)
    assert preview["valid"], preview
    result = await post(
        client, "/imports/apply", body | {"preview_token": preview["preview_token"]}, status=200
    )
    identifier = result["records"]["alias"]
    policy: dict[str, Any] = {
        "entity_type": "accounting.account_group_alias",
        "field_key": "alias",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    h = headers(policies=[policy])
    export = await client.get(BASE + "/exports/account-group-aliases", headers=h)
    assert export.status_code == 200, export.text
    assert export.json()["items"][0]["id"] == identifier
    assert "alias" not in export.json()["items"][0]
    assert export.headers["cache-control"] == "no-store"
    history = await client.get(BASE + "/history/account-group-aliases/" + identifier, headers=h)
    assert "alias" not in history.json()["items"][0]["changed_fields"]
