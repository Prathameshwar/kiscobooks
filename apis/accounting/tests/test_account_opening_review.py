"""Opening window drift is rejected at both native posting transaction boundaries."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from accounting.models.fiscal import FiscalPeriod
from accounting.models.ledger import Journal, JournalLine
from accounting.tasks.posting_delivery import deliver
from tests.conftest import COMPANY, TENANT
from tests.test_financial_opening_api import ROOT, body_for
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import ledger_headers, post_journal


async def prepared_opening(client, app):
    body = await body_for(client, app)
    response = await client.post(ROOT, json=body, headers=ledger_headers())
    assert response.status_code == 201, response.text
    row = response.json()
    response = await client.post(
        ROOT + f"/{row['id']}/prepare-drafts",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Reviewed opening",
        },
        headers=ledger_headers(),
    )
    assert response.status_code == 200, response.text
    journal = await client.get(
        BASE + "/journals/" + response.json()["journal_ids"][0], headers=ledger_headers()
    )
    assert journal.status_code == 200
    return row, journal.json()


async def close_later(app, status):
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            period = await db.scalar(
                select(FiscalPeriod).where(
                    FiscalPeriod.company_id == COMPANY,
                    FiscalPeriod.start_date <= dt.date(2026, 5, 1),
                    FiscalPeriod.end_date >= dt.date(2026, 5, 1),
                )
            )
            assert period is not None
            period.status = status


@pytest.mark.parametrize("status", ["CLOSED", "LOCKED"])
@pytest.mark.parametrize("during_reservation", [False, True])
async def test_opening_post_rechecks_later_books(
    client, app, monkeypatch, status, during_reservation
):
    _, journal = await prepared_opening(client, app)
    if during_reservation:
        original = app.state.posting_client.reserve

        async def reserve(*args, **kwargs):
            receipt = await original(*args, **kwargs)
            await close_later(app, status)
            return receipt

        monkeypatch.setattr(app.state.posting_client, "reserve", reserve)
    else:
        await close_later(app, status)
    posted = await post_journal(client, journal)
    assert posted.status_code == 409, posted.text
    assert "later closed or locked" in posted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(select(func.count(Journal.id)).where(Journal.status == "POSTED"))
                == 0
            )
            assert (
                await db.scalar(
                    select(func.count(JournalLine.id)).where(
                        JournalLine.journal_id == uuid.UUID(journal["id"])
                    )
                )
                == 2
            )
    current = (
        await client.get(BASE + f"/journals/{journal['id']}", headers=ledger_headers())
    ).json()
    assert current["status"] == ("PREPARED" if during_reservation else "DRAFT")
    if during_reservation:
        # The reserved intent can be cancelled through the native durable abort.
        cancelled = await client.post(
            BASE + f"/journals/{journal['id']}/void",
            json={"expected_version": current["row_version"], "reason": "Cancel blocked opening"},
            headers=ledger_headers(),
        )
        assert cancelled.status_code == 200, cancelled.text
        outcome = await deliver(app.state.session_factory, app.state.posting_client)
        assert outcome.confirmed == 1
        assert app.state.posting_client.receipts[uuid.UUID(journal["id"])].status == "aborted"


async def test_reconciliation_discloses_closed_later_books(client, app):
    row, journal = await prepared_opening(client, app)
    posted = await post_journal(client, journal)
    assert posted.status_code == 200, posted.text
    await deliver(app.state.session_factory, app.state.posting_client)
    await close_later(app, "CLOSED")
    response = await client.get(ROOT + f"/{row['id']}/reconciliation", headers=ledger_headers())
    assert response.status_code == 200, response.text
    assert "LATER_BOOKS_CLOSED" in response.json()["blockers"]
    assert not response.json()["ready_to_finalize"]


async def test_opening_recovery_is_scoped_read_only_and_retains_reversal_lineage(client, app):
    row, journal = await prepared_opening(client, app)
    path = ROOT + f"/{row['id']}/journals/{journal['id']}/recovery"
    assert (await client.get(path)).status_code == 401
    response = await client.get(path, headers=ledger_headers())
    assert response.status_code == 200, response.text
    assert response.json()["can_cancel"] and not response.json()["can_reverse"]
    assert "no-store" in response.headers["cache-control"]
    assert response.json()["reversal_journal_id"] is None
    posted = await post_journal(client, journal)
    assert posted.status_code == 200, posted.text
    await deliver(app.state.session_factory, app.state.posting_client)
    response = await client.get(path, headers=ledger_headers())
    assert response.json()["can_reverse"], response.text
    await close_later(app, "LOCKED")
    blocked = await client.get(path, headers=ledger_headers())
    assert not blocked.json()["can_reverse"]
    assert "LATER_BOOKS_CLOSED" in blocked.json()["reversal_blockers"]
    await close_later(app, "OPEN")
    created = await client.post(
        BASE + f"/journals/{journal['id']}/reversal",
        json={"posting_date": journal["posting_date"], "reason": "Correct opening source"},
        headers=ledger_headers(),
    )
    assert created.status_code == 201, created.text
    response = await client.get(path, headers=ledger_headers())
    assert response.json()["reversal_journal_id"] == created.json()["id"]
    assert response.json()["reversal_status"] == "DRAFT"
    assert not response.json()["can_reverse"]
    reversed_post = await post_journal(client, created.json())
    assert reversed_post.status_code == 200, reversed_post.text
    response = await client.get(path, headers=ledger_headers())
    assert response.json()["reversal_status"] == "POSTED"
    assert (await client.get(ROOT + f"/{row['id']}", headers=ledger_headers())).json()[
        "status"
    ] == "REVERSED"


async def test_opening_recovery_denies_scope_fields_and_missing_posting_authority(client, app):
    from billing_platform.ids import uuid7

    from tests.test_field_policy import policy
    from tests.test_ledger_api import LEDGER_PERMISSIONS

    row, journal = await prepared_opening(client, app)
    path = ROOT + f"/{row['id']}/journals/{journal['id']}/recovery"
    hidden = await client.get(
        path,
        headers=ledger_headers(policies=[policy("reversal_of_id", entity="accounting.journal")]),
    )
    assert hidden.status_code == 403, hidden.text
    no_ledger = await client.get(
        path, headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {"ledger.read"})
    )
    assert no_ledger.status_code == 403, no_ledger.text
    restricted = await client.get(
        path, headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {"ledger.post_journal"})
    )
    assert restricted.status_code == 200, restricted.text
    assert not restricted.json()["can_cancel"] and not restricted.json()["can_reverse"]
    no_period = await client.get(
        path, headers=ledger_headers(permissions=LEDGER_PERMISSIONS - {"period.post"})
    )
    assert no_period.json()["can_cancel"] and not no_period.json()["can_reverse"]
    wrong_company = uuid7()
    other = await client.get(
        path.replace(str(COMPANY), str(wrong_company)),
        headers=ledger_headers(company=wrong_company),
    )
    assert other.status_code in {403, 404}, other.text
    other_tenant = await client.get(path, headers=ledger_headers(tenant=uuid7()))
    assert other_tenant.status_code in {403, 404}, other_tenant.text


async def test_legacy_opening_post_also_rechecks_later_books(client, app):
    body = await body_for(client, app)
    created = await client.post(
        BASE + "/opening-batches",
        json={
            "posting_date": body["posting_date"],
            "description": "Legacy reviewed opening",
            "lines": [
                {key: value for key, value in entry.items() if key != "source_key"}
                for entry in body["entries"]
            ],
        },
        headers=ledger_headers(),
    )
    assert created.status_code == 201, created.text
    journal = (
        await client.get(
            BASE + "/journals/" + created.json()["journal_id"], headers=ledger_headers()
        )
    ).json()
    await close_later(app, "CLOSED")
    response = await post_journal(client, journal)
    assert response.status_code == 409, response.text


async def test_prepared_reversal_cancellation_recovery(client, app):
    row, journal = await prepared_opening(client, app)
    assert (await post_journal(client, journal)).status_code == 200
    await deliver(app.state.session_factory, app.state.posting_client)
    created = await client.post(
        BASE + f"/journals/{journal['id']}/reversal",
        json={"posting_date": journal["posting_date"], "reason": "Review corrected migration"},
        headers=ledger_headers(),
    )
    assert created.status_code == 201, created.text
    app.state.posting_client.fail = True
    interrupted = await post_journal(client, created.json())
    assert interrupted.status_code == 503, interrupted.text
    app.state.posting_client.fail = False
    path = ROOT + f"/{row['id']}/journals/{journal['id']}/recovery"
    recovery = (await client.get(path, headers=ledger_headers())).json()
    assert recovery["can_cancel_reversal"]
    assert recovery["reversal_status"] == "PREPARED"
    cancelled = await client.post(
        BASE + f"/journals/{created.json()['id']}/void",
        json={
            "expected_version": recovery["reversal_expected_version"],
            "reason": "Cancel interrupted reversal",
        },
        headers=ledger_headers(),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert (await deliver(app.state.session_factory, app.state.posting_client)).confirmed == 1
    recovery = (await client.get(path, headers=ledger_headers())).json()
    assert recovery["reversal_journal_id"] is None and recovery["can_reverse"]
