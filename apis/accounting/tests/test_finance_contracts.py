"""Financial metadata must carry complete nested input definitions."""

import json

import httpx
from fastapi import FastAPI

from tests.test_fiscal_api import BASE
from tests.test_ledger_api import journal_setup, ledger_headers


async def test_nested_financial_fields_resolve_without_missing_defs(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app)
    response = await client.get(BASE + "/finance/field-sets/journals", headers=ledger_headers())
    assert response.status_code == 200, response.text
    field = next(item for item in response.json()["fields"] if item["key"] == "lines")
    assert "#/$defs/" not in json.dumps(field["definition"])
    assert field["readable"] and field["writable"]


async def test_period_transition_reasons_have_protected_detail_and_exports(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from tests.test_finance_review2 import policy

    _, period, _ = await journal_setup(client, app)
    listed = await client.get(
        BASE + "/fiscal-transitions", params={"period_id": period["id"]}, headers=ledger_headers()
    )
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1, listed.text
    row = listed.json()["items"][0]
    assert "reason" not in row
    detail = await client.get(BASE + "/fiscal-transitions/" + row["id"], headers=ledger_headers())
    assert detail.status_code == 200 and detail.json()["reason"], detail.text
    exported = await client.get(
        BASE + "/exports/fiscal-transitions",
        headers=ledger_headers(policies=[policy("fiscal_transition", "reason")]),
    )
    assert (
        exported.status_code == 200 and "reason" not in exported.json()["items"][0]
    ), exported.text


def test_standalone_financial_contracts_are_current() -> None:
    from tools.export_financial_contracts import ROOT, documents

    for name, document in documents().items():
        assert (ROOT / (name + ".schema.json")).read_text(encoding="utf-8") == document


async def test_fiscal_exports_are_typed_and_field_protected(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from tests.test_finance_review2 import policy

    await journal_setup(client, app)
    for resource, entity, field, count in (
        ("financial-setup", "financial_setup", "timezone", 1),
        ("fiscal-years", "fiscal_year", "code", 1),
        ("fiscal-periods", "fiscal_period", "status", 12),
    ):
        response = await client.get(
            BASE + "/exports/" + resource, headers=ledger_headers(policies=[policy(entity, field)])
        )
        assert response.status_code == 200 and len(response.json()["items"]) == count, response.text
        assert all(field not in row for row in response.json()["items"])
