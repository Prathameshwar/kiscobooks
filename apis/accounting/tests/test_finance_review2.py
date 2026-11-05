"""Security review: nested field privacy and current workflow authority."""

import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.company_context import verify_company_context
from billing_platform.gateway import decode_actor_context
from fastapi import FastAPI

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.tasks.access import readable
from tests.conftest import COMPANY, SECRET
from tests.test_charges_api import approve, assessment, setup_charge
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers, post_journal
from tests.test_openings_sources import party_accounts, source


def policy(entity: str, field: str, **extra: Any) -> dict[str, Any]:
    return {
        "entity_type": "accounting." + entity,
        "field_key": field,
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        **extra,
    }


def access_with(*policies: dict[str, Any]) -> Access:
    h = ledger_headers(policies=list(policies))
    return Access(
        decode_actor_context(h["X-Actor-Context"], h["X-Actor-Signature"], SECRET.encode()),
        verify_company_context(h["X-Company-Context"], h["X-Company-Signature"], SECRET.encode()),
    )


@pytest.mark.parametrize(
    "entity,field,snapshot",
    [
        ("source_document", "amount", "payload"),
        ("opening_batch", "bills", "payload"),
        ("credit_reservation", "amount", "decision"),
        ("charge_assessment", "amount", "snapshot"),
        ("charge_tax_snapshot", "gross_amount", "snapshot"),
        ("open_item", "amount", "terms"),
    ],
)
def test_nested_snapshots_cannot_bypass_field_read_denial(
    entity: str, field: str, snapshot: str
) -> None:
    spec = FINANCIAL_BY_NAME[entity]
    assert snapshot in spec.detail.model_fields
    assert snapshot not in readable(access_with(policy(entity, field)), spec)


def test_numeric_condition_compares_money_numerically() -> None:
    spec = FINANCIAL_BY_NAME["source_document"]
    rule = policy(
        "source_document", "amount", condition={"field": "amount", "cmp": "gt", "value": "20"}
    )
    assert "amount" not in readable(access_with(rule), spec, {"amount": Decimal("100.0000")})
    assert "amount" in readable(access_with(rule), spec, {"amount": Decimal("9.0000")})


async def test_source_snapshot_is_redacted_in_detail_and_export(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    _, account, _ = await party_accounts(client)
    row = await source(client, account, journal["lines"][1]["account_id"])
    h = ledger_headers(policies=[policy("source_document", "amount")])
    detail = await client.get(BASE + "/source-documents/" + row["id"], headers=h)
    assert detail.status_code == 200 and "payload" not in detail.json(), detail.text
    exported = await client.get(BASE + "/exports/source-documents", headers=h)
    assert (
        exported.status_code == 200 and "payload" not in exported.json()["items"][0]
    ), exported.text


async def test_charge_post_replay_and_reversal_require_current_workflow_permissions(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _, _ = await setup_charge(client, app)
    row = await assessment(client, body)
    approved = await approve(client, row)
    assert approved.status_code == 200
    journal = (
        await client.get(
            BASE + "/journals/" + approved.json()["journal_id"], headers=ledger_headers()
        )
    ).json()
    key = str(uuid.uuid4())
    assert (await post_journal(client, journal, key=key)).status_code == 200
    denied = await post_journal(
        client, journal, key=key, permissions=LEDGER_PERMISSIONS - {"accounting.charges.manage"}
    )
    assert denied.status_code == 403, denied.text
    reverse = await client.post(
        BASE + "/journals/" + journal["id"] + "/reversal",
        json={"posting_date": "2026-04-14", "reason": "Requires charge approver"},
        headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {"accounting.charges.approve"}),
    )
    assert reverse.status_code == 403, reverse.text


async def test_charge_policy_accepts_maximum_end_date(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _, _ = await setup_charge(client, app)
    result = await client.post(
        BASE + "/charge-policies/" + body["policy_id"] + "/close",
        json={"expected_version": 1, "valid_to": "9999-12-31"},
        headers=ledger_headers(),
    )
    assert result.status_code == 200, result.text


async def test_input_only_fields_enforce_write_denials(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app, zero_opening=False)
    opening = {
        "posting_date": "2026-04-01",
        "description": "Initial opening",
        "lines": journal["lines"],
    }
    denied = await client.post(
        BASE + "/opening-batches",
        json=opening,
        headers=ledger_headers(policies=[policy("opening_batch", "lines", access="write")]),
    )
    assert denied.status_code == 403, denied.text
    _, account, _ = await party_accounts(client)
    source_body = {
        "kind": "INVOICE",
        "account_id": account["id"],
        "counterpart_account_id": journal["lines"][1]["account_id"],
        "currency": "INR",
        "amount": "10",
        "exchange_rate": "1",
        "document_date": "2026-04-02",
        "posting_date": "2026-04-02",
        "due_date": "2026-05-01",
        "reference": "INV-PERMISSION",
        "source_system": "billing",
        "source_type": "invoice",
        "source_id": str(uuid.uuid4()),
        "description": "Denied due date",
    }
    denied = await client.post(
        BASE + "/source-documents",
        json=source_body,
        headers=ledger_headers(policies=[policy("source_document", "due_date", access="write")]),
    )
    assert denied.status_code == 403, denied.text


@pytest.mark.parametrize(
    "origin",
    [
        "http://identity.test",
        "https://identity.test/path",
        "https://user:secret@identity.test",
        "https://identity.test/?token=x",
        "https://identity.test/#fragment",
    ],
)
def test_posting_origin_is_rejected_before_opening_an_http_client(origin: str) -> None:
    from pydantic import ValidationError

    from accounting.config import Settings

    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "database_url": "sqlite+aiosqlite:///:memory:",
                "actor_signing_secret": SECRET,
                "identity_posting_url": origin,
                "identity_posting_key_id": "current",
                "identity_posting_secret": SECRET,
                "identity_posting_response_keys": {"current": SECRET},
            }
        )


async def test_realized_fx_obeys_field_privacy_and_can_reverse_retired_offsets(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from tests.test_allocations import allocate, items
    from tests.test_openings_sources import post_source

    journal, _, _ = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client, currency="USD")
    invoice = await source(
        client, customer, journal["lines"][1]["account_id"], currency="USD", rate="83"
    )
    receipt = await source(
        client,
        customer,
        journal["lines"][0]["account_id"],
        kind="RECEIPT",
        currency="USD",
        rate="84",
        date="2026-04-05",
    )
    assert (await post_source(client, invoice)).status_code == 200
    assert (await post_source(client, receipt)).status_code == 200
    current = await items(client)
    debt, credit = (
        next(i for i in current if i["direction"] == side) for side in ("DEBT", "CREDIT")
    )
    accounts = (await client.get(BASE + "/accounts?limit=200", headers=ledger_headers())).json()[
        "items"
    ]
    offset = next(a for a in accounts if a["code"] == "ROUNDING_GAIN")
    from tests.test_masters import activate, post

    offset = await post(
        client,
        "/accounts",
        {
            "code": "FX_CUSTOM",
            "name": "Exchange gains",
            "group_id": offset["group_id"],
            "kind": "GENERAL",
        },
    )
    offset = await activate(client, "/accounts", offset)
    body = {
        "debt_item_id": debt["id"],
        "credit_item_id": credit["id"],
        "posting_date": "2026-04-05",
        "amount": "100",
        "fx_account_id": offset["id"],
    }
    denied = await client.post(
        BASE + "/allocations",
        json=body,
        headers=ledger_headers(features={"multi_currency"}, policies=[policy("account", "kind")]),
    )
    assert denied.status_code == 403, denied.text
    allocated = await allocate(
        client, debt, credit, "100", "2026-04-05", fx_account_id=offset["id"]
    )
    assert allocated.status_code == 201, allocated.text
    current_offset = (
        await client.get(BASE + "/accounts/" + offset["id"], headers=ledger_headers())
    ).json()
    assert current_offset["used_at"]
    retired = await client.post(
        BASE + "/accounts/" + offset["id"] + "/deactivate",
        json={"expected_version": current_offset["row_version"]},
        headers=ledger_headers(),
    )
    assert retired.status_code == 200, retired.text
    reverse = await client.post(
        BASE + "/allocations/" + allocated.json()["id"] + "/reverse",
        json={
            "expected_version": allocated.json()["row_version"],
            "posting_date": "2026-04-06",
            "reason": "Reverse original exchange posting",
        },
        headers=ledger_headers(features={"multi_currency"}),
    )
    assert reverse.status_code == 200, reverse.text


async def test_current_timezone_does_not_become_an_immutable_posting_setting(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from tests.test_fiscal_api import facts
    from tests.test_ledger_api import create_journal

    journal, _, _ = await journal_setup(client, app)
    draft = await create_journal(client, journal)
    result = await post_journal(
        client, draft, finance=facts().model_copy(update={"timezone": "UTC"})
    )
    assert result.status_code == 200, result.text
