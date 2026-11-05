"""Native purchase evidence, partial claims, idempotency and stale-history guards."""

from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from accounting.models.invoice_credit import InvoiceCreditEvent
from tests.conftest import TENANT
from tests.invoice_helpers import posted_purchase
from tests.test_fiscal_api import BASE
from tests.test_voucher_tax import th


def action(component, **changes):
    return {
        "component_id": str(component.id),
        "expected_event_id": str(component.id),
        "kind": "VERIFY",
        "amount": "180",
        "event_date": "2026-04-03",
        "posting_date": "2026-04-03",
        "document_verified": True,
        "supply_received": True,
        "business_use": True,
        "restrictions_checked": True,
        "supplier_report_matched": True,
        "tax_payment_verified": True,
        "return_filed": True,
        "supplier_paid": False,
        "reference": "Retained GSTR evidence / supplier document",
        "evidence_sha256": "a" * 64,
        "reason": "Reviewed ordinary service input credit",
    } | changes


async def balance(client, component):
    response = await client.get(
        BASE + f"/invoice-tax-components/{component.id}/credit-position", headers=th()
    )
    assert response.status_code == 200, response.text
    return response.json()


async def post_action(client, row):
    journal = await client.get(BASE + f"/journals/{row['journal_id']}", headers=th())
    assert journal.status_code == 200, journal.text
    return await client.post(
        BASE + f"/journals/{row['journal_id']}/post",
        json={"expected_version": journal.json()["row_version"]},
        headers=th(),
    )


async def test_verified_credit_claim_is_atomic_replayable_and_guarded(client, app):
    data = await posted_purchase(client, app)
    component = data["component"]
    initial = await balance(client, component)
    assert initial["pending"] == "180.0000" and initial["claimed"] == "0.0000"
    before_verify = await client.post(
        BASE + "/invoice-credit-actions", json=action(component, kind="CLAIM"), headers=th()
    )
    assert before_verify.status_code == 422, before_verify.text
    headers = th()
    verified = await client.post(
        BASE + "/invoice-credit-actions", json=action(component), headers=headers
    )
    assert verified.status_code == 201, verified.text
    assert verified.json()["journal_id"] is None
    assert (
        await client.post(BASE + "/invoice-credit-actions", json=action(component), headers=headers)
    ).json() == verified.json()
    current = await balance(client, component)
    assert current["eligible_unclaimed"] == "180.0000"
    body = action(
        component, kind="CLAIM", amount="100", expected_event_id=current["latest_event_id"]
    )
    draft = await client.post(BASE + "/invoice-credit-actions", json=body, headers=th())
    assert draft.status_code == 201, draft.text
    assert (await balance(client, component))["claimed"] == "0.0000"
    competing = await client.post(BASE + "/invoice-credit-actions", json=body, headers=th())
    assert competing.status_code == 201, competing.text
    if app.state.engine.dialect.name == "mysql":
        import asyncio

        results = await asyncio.gather(
            post_action(client, draft.json()), post_action(client, competing.json())
        )
        assert sorted(row.status_code for row in results) == [200, 409], [
            row.text for row in results
        ]
        winning = draft.json() if results[0].status_code == 200 else competing.json()
    else:
        posted = await post_action(client, draft.json())
        assert posted.status_code == 200, posted.text
        stale = await post_action(client, competing.json())
        assert stale.status_code == 409, stale.text
        winning = draft.json()
    assert (await balance(client, component))["claimed"] == "100.0000"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(InvoiceCreditEvent.id))) == 2
    reverse = await client.post(
        BASE + f"/journals/{winning['journal_id']}/reversal",
        json={
            "posting_date": "2026-04-04",
            "reason": "Tax correction must retain statutory history",
        },
        headers=th(),
    )
    assert reverse.status_code == 409, reverse.text


async def test_credit_evidence_permissions_read_denies_and_rcm_cash_requirement(client, app):
    data = await posted_purchase(client, app, reverse=True)
    component = data["component"]
    response = await client.post(
        BASE + "/invoice-credit-actions", json=action(component), headers=th()
    )
    assert response.status_code == 422 and "cash discharge" in response.text
    response = await client.post(
        BASE + "/invoice-credit-actions", json=action(component), headers={}
    )
    assert response.status_code == 401
    response = await client.post(
        BASE + "/invoice-credit-actions",
        json=action(component),
        headers=th(permissions={"ledger.read"}),
    )
    assert response.status_code == 403
    response = await client.get(
        BASE + f"/invoice-tax-components/{component.id}/credit-position",
        headers=th(
            policies=[
                {
                    "entity_type": "accounting.invoice_tax_component",
                    "field_key": "amount",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(data["invoice"].company_id),
                }
            ]
        ),
    )
    assert response.status_code == 403
    for amount in (0, "-1", "0.00001", True, 0.5, "NaN", "Infinity"):
        response = await client.post(
            BASE + "/invoice-credit-actions", json=action(component, amount=amount), headers=th()
        )
        assert response.status_code == 422, response.text


async def test_blocked_credit_reclassifies_pending_and_rcm_uses_cash_offsets(client, app):
    from tests.test_fiscal_api import change
    from tests.test_masters import activate
    from tests.test_tax_mappings import gst
    from tests.test_voucher_tax import MH, line, send

    data = await posted_purchase(client, app, reverse=True)
    component = data["component"]
    blocked = await client.post(
        BASE + "/invoice-credit-actions",
        json=action(component, kind="BLOCK", amount="30", offset_account_id=data["expense"]["id"]),
        headers=th(),
    )
    assert blocked.status_code == 201, blocked.text
    posted = await post_action(client, blocked.json())
    assert posted.status_code == 200, posted.text
    assert (await balance(client, component))["blocked"] == "30.0000"

    periods = (await client.get(BASE + "/fiscal-periods?limit=20", headers=th())).json()["items"]
    june = next(row for row in periods if row["start_date"] == "2026-06-01")
    assert (await change(client, june, "OPEN")).status_code == 200
    deposit = await send(
        client,
        "/accounts",
        {
            "code": "GST_CASH_DEPOSIT",
            "name": "GST statutory cash deposit",
            "group_id": data["groups"]["ADVANCES"],
            "kind": "TAX",
        },
    )
    await send(
        client, "/account-tax-profiles", {"account_id": deposit["id"]} | gst("IGST", "DEPOSIT", MH)
    )
    deposit = await activate(client, "/accounts", deposit, h=th())
    deposited = await send(
        client,
        "/journals",
        {
            "document_date": "2026-06-01",
            "posting_date": "2026-06-01",
            "description": "Statutory cash ledger funding",
            "lines": [line(deposit, "DEBIT", "180"), line(data["cash"], "CREDIT", "180")],
        },
    )
    paid = await client.post(
        BASE + f"/journals/{deposited['id']}/post",
        json={"expected_version": deposited["row_version"]},
        headers=th(),
    )
    assert paid.status_code == 200, paid.text
    import uuid

    from accounting.models.ledger import JournalLine

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            deposit_line = await db.scalar(
                select(JournalLine).where(
                    JournalLine.journal_id == uuid.UUID(deposited["id"]),
                    JournalLine.side == "DEBIT",
                )
            )
    current = await balance(client, component)
    discharged = await client.post(
        BASE + "/invoice-credit-actions",
        json=action(
            component,
            kind="RCM_DISCHARGE",
            expected_event_id=current["latest_event_id"],
            event_date="2026-06-02",
            posting_date="2026-06-02",
            cash_deposit_line_id=str(deposit_line.id),
        ),
        headers=th(),
    )
    assert discharged.status_code == 201, discharged.text
    posted = await post_action(client, discharged.json())
    assert posted.status_code == 200, posted.text
    current = await balance(client, component)
    assert current["rcm_discharged"] == "180.0000"
    verified = await client.post(
        BASE + "/invoice-credit-actions",
        json=action(
            component,
            amount="150",
            expected_event_id=current["latest_event_id"],
            event_date="2026-06-03",
            posting_date="2026-06-03",
        ),
        headers=th(),
    )
    assert verified.status_code == 201, verified.text
    assert (await balance(client, component))["eligible_unclaimed"] == "150.0000"
    reversed_deposit = await client.post(
        BASE + f"/journals/{deposited['id']}/reversal",
        json={"posting_date": "2026-06-04", "reason": "Already consumed statutory deposit"},
        headers=th(),
    )
    assert reversed_deposit.status_code == 409, reversed_deposit.text
