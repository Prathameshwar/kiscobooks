"""Pre-cutover native history requires explicit, reconciled, one-way adoption."""

import pytest
from billing_platform.errors import ConflictError

from accounting.tasks import stock_opening_control
from accounting.tasks.stock_execution import _dispatch
from tests.conftest import SECRET
from tests.test_ledger_api import journal_setup
from tests.test_stock_effects import Source, captured, configure, source
from tests.test_stock_ledger import item, warehouse
from tests.test_stock_opening_api import BASE, auth, manifest
from tests.test_stock_opening_cohorts import settle_posting_delivery


async def test_legacy_native_history_is_adopted_without_new_stock_or_journal(
    client, app, monkeypatch
):
    _, period, owner = await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    product, location = item(), warehouse()
    request = captured(period, product, location)
    with pytest.raises(ConflictError, match="confirm zero stock"):
        await _dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=Source(source(request, product, location)),
            enabled=True,
        )

    # Emulate only the absence of the new cutover fence in the previous release.
    # The real native compiler, journal, owner receipt and delivery worker still
    # create every underlying effect; no balance or execution receipt is fabricated.
    async def previous_release_gate(db, company, body):
        return None

    with monkeypatch.context() as previous:
        previous.setattr(stock_opening_control, "require_posting", previous_release_gate)
        result, _ = await _dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=Source(source(request, product, location)),
            enabled=True,
        )
    assert result.outcome == "COMMITTED"
    ready = await client.get(BASE + "/readiness", headers=auth())
    assert ready.status_code == 200 and ready.json()["status"] == "LEGACY_ACTIVITY"
    assert not ready.json()["can_start"]
    body = manifest() | {
        "adopt_existing": True,
        "reason": "Reviewed existing native stock and GL history",
    }
    assert (await client.post(BASE + "/adopt", json=body, headers=auth())).status_code == 409
    await settle_posting_delivery(app, owner)
    adopted = await client.post(BASE + "/adopt", json=body, headers=auth())
    assert adopted.status_code == 201, adopted.text
    row = adopted.json()
    assert row["status"] == "FINALIZED" and row["legacy_adopted"] and row["expected_cohorts"] == 0
    blocked = await client.post(
        BASE + f"/{row['id']}/reopen",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Attempt to convert legacy adoption to another opening",
        },
        headers=auth(),
    )
    assert blocked.status_code == 409 and "legacy adoption" in blocked.text
