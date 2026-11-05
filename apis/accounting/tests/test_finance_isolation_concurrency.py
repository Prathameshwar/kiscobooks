"""Every financial table contains two tenants; native races exercise company serialization."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.metadata import service_metadata
from accounting.models.charges import ChargeTaxSnapshot
from accounting.models.masters import Record
from tests.conftest import COMPANY, TENANT, USER
from tests.test_allocations import allocate, items
from tests.test_charges_api import approve, assessment, setup_charge
from tests.test_credit_api import policy, request
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import create_journal, journal_setup, ledger_headers, post_journal
from tests.test_openings_sources import party_accounts, post_source, source


async def test_every_financial_table_isolates_two_populated_tenants(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, account, journal, _ = await setup_charge(client, app)
    row = await assessment(client, body)
    approved = await approve(client, row)
    assert approved.status_code == 200
    assert (await post_source(client, approved.json())).status_code == 200
    payment = await source(
        client,
        account,
        journal["lines"][0]["account_id"],
        kind="RECEIPT",
        amount="50",
        date="2026-04-15",
    )
    assert (await post_source(client, payment)).status_code == 200
    current = await items(client)
    debt = next(item for item in current if item["id"] == body["item_id"])
    credit = next(item for item in current if item["direction"] == "CREDIT")
    assert (await allocate(client, debt, credit, "50", "2026-04-15")).status_code == 201
    reservation = await client.post(
        BASE + "/credit-reservations", json=request(account), headers=ledger_headers()
    )
    assert reservation.status_code == 201, reservation.text
    await policy(client, {"id": account["party_id"]}, enforcement="OVERRIDE", limit_amount="0")
    override = await client.post(
        BASE + "/credit-overrides",
        json=request(account) | {"reason": "Fixture authorization"},
        headers=ledger_headers(features={"credit_limits"}),
    )
    assert override.status_code == 201, override.text
    # Populate each new money grain through its real posting boundary before cloning tenants.
    from accounting.models.fiscal import FiscalPeriod
    from accounting.tasks.voucher_money_execution import dispatch
    from tests.conftest import SECRET
    from tests.test_money_profiles import revise
    from tests.test_voucher_money import money_command

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            period = await db.scalar(select(FiscalPeriod).where(FiscalPeriod.status == "OPEN"))
            evidence = {"id": str(period.id), "row_version": period.row_version}
    captured = journal | {
        "posting_date": "2026-04-15",
        "lines": [
            journal["lines"][0] | {"amount": "25"},
            journal["lines"][1] | {"account_id": account["id"], "amount": "25"},
        ],
    }
    command = await money_command(app, captured, evidence)
    financial = command.source_payload["financial"]
    financial["accounts"][1]["tracking"] = "ON_ACCOUNT"
    financial["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"item_id": debt["id"]},
            "credit": {"line_key": financial["accounts"][1]["line_key"]},
            "currency": "INR",
            "amount": "25",
        }
    ]
    import datetime as dt

    from voucher_execution.transport import command_digest

    command = revise(command, kind="RECEIPT", financial=financial).model_copy(
        update={"posting_date": dt.date(2026, 4, 15)}
    )
    command = command.model_copy(update={"request_hash": command_digest(command)})
    posted = await dispatch(
        app.state.session_factory, command, secret=SECRET.encode(), client=app.state.posting_client
    )
    assert posted.outcome == "COMMITTED", posted
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                ChargeTaxSnapshot(
                    id=uuid7(),
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    assessment_id=uuid.UUID(row["id"]),
                    provider_id=uuid7(),
                    currency="INR",
                    net_amount="1",
                    gross_amount="1",
                    input_hash=row["input_hash"],
                    key_id="fixture",
                    snapshot={"fixture": True},
                    created_by=USER,
                    updated_by=USER,
                )
            )
    models = {
        mapper.class_.__tablename__: mapper.class_
        for mapper in Record.registry.mappers
        if issubclass(mapper.class_, Record)
    }
    expected = {
        "financial_setup",
        "fiscal_year",
        "fiscal_period",
        "fiscal_status_transition",
        "document_sequence",
        "journal",
        "journal_line",
        "opening_batch",
        "source_document",
        "open_item",
        "allocation",
        "credit_override",
        "credit_reservation",
        "charge_policy",
        "charge_assessment",
        "charge_tax_snapshot",
        "voucher_money_intent",
        "bank_instrument",
        "bank_instrument_event",
        "voucher_money_allocation",
    }
    originals: dict[str, list[dict[str, Any]]] = {}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            for table in service_metadata().sorted_tables:
                if table.name not in models:
                    continue
                records = list(
                    await db.scalars(select(models[table.name]).order_by(models[table.name].id))
                )
                originals[table.name] = [
                    {
                        column.key: getattr(record, column.key)
                        for column in table.columns
                        if column.computed is None
                    }
                    for record in records
                ]
    assert all(originals[name] for name in expected), {
        name for name in expected if not originals[name]
    }
    other_tenant, other_company = uuid7(), uuid7()
    ids = {TENANT: other_tenant, COMPANY: other_company}

    def remap(value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return ids.setdefault(value, uuid7())
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        if isinstance(value, list):
            return [remap(item) for item in value]
        return value

    with tenant_scope(other_tenant):
        async with app.state.session_factory() as db, db.begin():
            for name, records in originals.items():
                for record in records:
                    db.add(models[name](**remap(record)))
                    await db.flush()
    for tenant, company in ((TENANT, COMPANY), (other_tenant, other_company)):
        with tenant_scope(tenant):
            async with app.state.session_factory() as db:
                for name in expected:
                    stored = list(await db.scalars(select(models[name])))
                    assert len(stored) == len(originals[name]), name
                    assert all(
                        row.tenant_id == tenant and row.company_id == company for row in stored
                    ), name
                    foreign = (
                        ids[originals[name][0]["id"]]
                        if tenant == TENANT
                        else originals[name][0]["id"]
                    )
                    assert await db.get(models[name], foreign) is None, name


@pytest.mark.mysql
async def test_native_races_serialize_numbers_credit_allocation_and_charge_coverage(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    if app.state.engine.dialect.name != "mysql":
        pytest.skip("row-lock races require native MySQL")
    journal, _, _ = await journal_setup(client, app)
    one = await create_journal(client, journal)
    two = await create_journal(client, journal)
    posted = await asyncio.gather(post_journal(client, one), post_journal(client, two))
    assert [r.status_code for r in posted] == [200, 200], [r.text for r in posted]
    assert len({r.json()["number"] for r in posted}) == 2
    p, account, _ = await party_accounts(client)
    await policy(client, p)
    reservations = await asyncio.gather(
        *[
            client.post(
                BASE + "/credit-reservations",
                json=request(account),
                headers=ledger_headers(features={"credit_limits"}),
            )
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in reservations) == [201, 409], [r.text for r in reservations]
    active = next(r.json() for r in reservations if r.status_code == 201)
    released = await client.post(
        BASE + f"/credit-reservations/{active['id']}/release",
        json={"expected_version": 1},
        headers=ledger_headers(),
    )
    assert released.status_code == 200
    invoice = await source(
        client, account, journal["lines"][1]["account_id"], due_date="2026-04-02"
    )
    assert (await post_source(client, invoice)).status_code == 200
    payment = await source(client, account, journal["lines"][0]["account_id"], kind="RECEIPT")
    assert (await post_source(client, payment)).status_code == 200
    current = await items(client)
    debt = next(i for i in current if i["direction"] == "DEBT")
    credit = next(i for i in current if i["direction"] == "CREDIT")
    allocated = await asyncio.gather(
        *[allocate(client, debt, credit, "60", "2026-04-03") for _ in range(2)]
    )
    assert sorted(r.status_code for r in allocated) == [201, 422], [r.text for r in allocated]
    policy_response = await client.post(
        BASE + "/charge-policies",
        json={
            "account_id": account["id"],
            "offset_account_id": journal["lines"][1]["account_id"],
            "currency": "INR",
            "valid_from": "2026-04-01",
            "accrual_start_date": "2026-04-01",
            "method": "FIXED",
            "rate": "10",
            "tax_treatment": "NON_TAXABLE",
            "tax_reason": "Fixture exemption",
        },
        headers=ledger_headers(),
    )
    assert policy_response.status_code == 201
    body = {
        "item_id": debt["id"],
        "policy_id": policy_response.json()["id"],
        "coverage_end_date": "2026-04-13",
        "posting_date": "2026-04-13",
        "due_date": "2026-04-20",
        "exchange_rate": "1",
    }
    assessed = await asyncio.gather(
        *[
            client.post(BASE + "/charge-assessments", json=body, headers=ledger_headers())
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in assessed) == [201, 409], [r.text for r in assessed]
    charge = next(r.json() for r in assessed if r.status_code == 201)
    approvals = await asyncio.gather(approve(client, charge), approve(client, charge))
    assert sorted(r.status_code for r in approvals) == [200, 409], [r.text for r in approvals]
