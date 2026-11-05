"""Bank evidence reads cannot cross field, company or cursor scopes."""

import datetime as dt

from billing_platform.ids import uuid7
from voucher_execution.transport import command_digest

from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import COMPANY, SECRET
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_money_profiles import revise
from tests.test_voucher_money import delegated, money_command


def denied(entity, field):
    return ledger_headers(
        policies=[
            {
                "entity_type": "accounting." + entity,
                "field_key": field,
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )


async def test_instrument_and_history_pages_bind_filters_and_live_field_authority(client, app):
    original, period, owner = await journal_setup(client, app)
    command = await money_command(app, original, period)
    money = command.source_payload["financial"]
    tender = money["tenders"][0]
    money["tenders"] = [
        tender | {"amount": "40.0000"},
        tender | {"tender_key": str(uuid7()), "amount": "60.2500"},
    ]
    command = revise(command, financial=money)
    assert (
        await dispatch(app.state.session_factory, command, secret=SECRET.encode(), client=owner)
    ).outcome == "COMMITTED"
    path = BASE + "/bank-instruments"
    params = {
        "account_id": original["lines"][0]["account_id"],
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
        "limit": "1",
    }
    first = await client.get(path, params=params, headers=ledger_headers())
    assert first.status_code == 200, first.text
    cursor = first.json()["page"]["next_cursor"]
    assert cursor
    second = await client.get(path, params=params | {"cursor": cursor}, headers=ledger_headers())
    assert second.status_code == 200 and not second.json()["page"]["has_more"]
    identity = first.json()["items"][0]["id"]
    assert second.json()["items"][0]["id"] != identity
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=ledger_headers(permissions=set()))).status_code == 403
    for values in (
        params | {"cursor": "invalid"},
        params | {"cursor": cursor, "date_to": "2026-04-29"},
        params | {"date_from": "2026-05-01"},
        params | {"unsupported": "value"},
    ):
        assert (await client.get(path, params=values, headers=ledger_headers())).status_code == 422
    for field in ("account_id", "booking_date"):
        assert (
            await client.get(path, params=params, headers=denied("bank_instrument", field))
        ).status_code == 403
    detail = await client.get(path + f"/{identity}", headers=ledger_headers())
    assert detail.status_code == 200 and detail.json()["amount"] == "40.0000"
    hidden = await client.get(path + f"/{identity}", headers=denied("bank_instrument", "amount"))
    assert hidden.status_code == 200 and hidden.json().get("amount") is None
    other = uuid7()
    assert (
        await client.get(
            path.replace(str(COMPANY), str(other)) + f"/{identity}",
            headers=ledger_headers(company=other),
        )
    ).status_code == 403

    reverse = command.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": command.execution_id,
            "correction_reason": "Correct mistaken split cash entry",
            "posting_date": dt.date(2026, 4, 3),
            "execution_id": uuid7(),
            "operation_id": uuid7(),
            "authority": delegated(),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    assert (
        await dispatch(app.state.session_factory, reverse, secret=SECRET.encode(), client=owner)
    ).outcome == "COMMITTED"
    history = path + f"/{identity}/events"
    page = await client.get(history, params={"limit": 1}, headers=ledger_headers())
    assert page.status_code == 200
    assert page.json()["items"][0]["action"] == "BOOKED"
    cursor = page.json()["page"]["next_cursor"]
    last = await client.get(
        history, params={"limit": 1, "cursor": cursor}, headers=ledger_headers()
    )
    assert last.status_code == 200 and not last.json()["page"]["has_more"]
    assert last.json()["items"][0]["action"] == "REVERSED"
    assert (
        await client.get(history, params={"cursor": "invalid"}, headers=ledger_headers())
    ).status_code == 422
    assert (
        await client.get(history, headers=denied("bank_instrument_event", "instrument_id"))
    ).status_code == 403
    assert (
        await client.get(
            history,
            params={"limit": 1, "cursor": cursor},
            headers=denied("bank_instrument_event", "reason"),
        )
    ).status_code == 422
