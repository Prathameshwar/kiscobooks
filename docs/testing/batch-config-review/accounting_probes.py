"""Review probes assert observed defects; these are not fixed-behavior regressions.

Run with Accounting's virtualenv from apis/accounting.
"""

import datetime as dt

from accounting.api import stock_tracking as api
from tests.conftest import headers
from tests.test_masters import prepare
from tests.test_stock_tracking import BASE, KEYS, batch, facts

pytest_plugins = ["tests.conftest"]


async def test_date_correction_rejects_expiry_with_feature_disabled(client, monkeypatch):
    await prepare(client)

    async def verified(request, current, item, **kwargs):
        return facts(current.context.company_id, item).model_copy(update={
            "serial_tracking": False, "requirements": [], "expiry_required": False,
            "manufacture_date_required": False,
        })

    monkeypatch.setattr(api, "source", verified)
    auth = headers(permissions=KEYS, features={"inventory", "batch_tracking"})
    created = await client.post(BASE + "/batches", headers=auth, json=batch(
        manufactured_on=None, expires_on=None,
    ))
    assert created.status_code == 201, created.text
    row = created.json()
    corrected = await client.patch(BASE + "/batches/" + row["id"], headers=auth, json={
        "expected_version": row["row_version"], "expires_on": "2028-01-01",
        "reason": "Review disabled expiry feature admission",
    })
    assert corrected.status_code == 422, corrected.text
    unchanged = await client.get(BASE + "/batches/" + row["id"], headers=auth)
    assert unchanged.json()["expires_on"] is None


def test_shelf_life_is_unchecked_without_optional_manufacture_date():
    from accounting.domain.stock_tracking import validate_dates

    source = facts().model_copy(update={
        "manufacture_date_required": False, "shelf_life_days": 30,
    })
    validate_dates(source, None, dt.date(2090, 1, 1))
