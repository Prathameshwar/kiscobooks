"""Versioned issue numbering rules for non-statutory voucher documents."""

import datetime as dt
import uuid

from billing_platform.db import tenant_scope
from conftest import PERMISSIONS, TENANT, headers
from sqlalchemy import select
from test_foundation import create_type, draft

from vouchers.models import core as m


async def _issue(client, prefix, revision_id, series_id, **options):
    voucher, _ = await draft(client, prefix, revision_id)
    return await client.post(
        prefix + f"/vouchers/{voucher['id']}/issue",
        headers=headers(),
        json={"expected_version": 1, "series_id": series_id} | options,
    )


async def test_automatic_series_prefix_suffix_start_and_rejection(client, prefix):
    kind = await create_type(client, prefix, policy={"approval_required": False})
    series = await client.post(
        prefix + "/voucher-series",
        headers=headers(),
        json={
            "code": "AUTOMATIC",
            "prefix": "Q-",
            "suffix": "-A",
            "padding": 4,
            "start_value": 37,
            "include_year": False,
        },
    )
    assert series.status_code == 201, series.text
    series_id = series.json()["id"]
    denied = await _issue(client, prefix, kind["revision_id"], series_id, requested_sequence=99)
    assert denied.status_code == 422, denied.text
    first = await _issue(client, prefix, kind["revision_id"], series_id)
    second = await _issue(client, prefix, kind["revision_id"], series_id)
    assert first.status_code == second.status_code == 200
    assert [first.json()["issue_number"], second.json()["issue_number"]] == [
        "Q-0037-A", "Q-0038-A"
    ]


async def test_override_requires_reason_permission_and_advances_high_water(client, prefix):
    kind = await create_type(client, prefix, policy={"approval_required": False})
    series = (
        await client.post(
            prefix + "/voucher-series",
            headers=headers(),
            json={"code": "OVERRIDE", "numbering_mode": "AUTOMATIC_WITH_OVERRIDE"},
        )
    ).json()
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    path = prefix + f"/vouchers/{voucher['id']}/issue"
    body = {"expected_version": 1, "series_id": series["id"], "requested_sequence": 12}
    missing_reason = await client.post(path, headers=headers(), json=body)
    assert missing_reason.status_code == 422
    denied = await client.post(
        path,
        headers=headers(permissions=PERMISSIONS - {"vouchers.series.manage"}),
        json=body | {"reason": "Previously allocated externally"},
    )
    assert denied.status_code == 403, denied.text
    issued = await client.post(
        path, headers=headers(), json=body | {"reason": "Previously allocated externally"}
    )
    assert issued.status_code == 200, issued.text
    next_one = await _issue(client, prefix, kind["revision_id"], series["id"])
    assert issued.json()["issue_number"].endswith("000012")
    assert next_one.json()["issue_number"].endswith("000013")


async def test_manual_series_requires_canonical_number_and_preserves_counter(client, prefix, app):
    kind = await create_type(client, prefix, policy={"approval_required": False})
    series = (
        await client.post(
            prefix + "/voucher-series",
            headers=headers(),
            json={
                "code": "MANUAL",
                "prefix": "M-",
                "suffix": "-X",
                "padding": 3,
                "start_value": 5,
                "numbering_mode": "MANUAL",
                "include_year": False,
            },
        )
    ).json()
    series_id = series["id"]
    missing = await _issue(client, prefix, kind["revision_id"], series_id)
    malformed = await _issue(client, prefix, kind["revision_id"], series_id, manual_number="M-5-X")
    assert missing.status_code == malformed.status_code == 422
    issued = await _issue(client, prefix, kind["revision_id"], series_id, manual_number="M-005-X")
    duplicate = await _issue(
        client, prefix, kind["revision_id"], series_id, manual_number="M-005-X"
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["issue_number"] == "M-005-X"
    assert duplicate.status_code == 409, duplicate.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            counters = list(
                await db.scalars(
                    select(m.VoucherNumberCounter).where(
                        m.VoucherNumberCounter.series_id == uuid.UUID(series_id)
                    )
                )
            )
            assert counters == []


async def test_continuous_series_uses_fixed_reset_key(client, prefix, app):
    series = (
        await client.post(
            prefix + "/voucher-series",
            headers=headers(),
            json={"code": "CONTINUOUS", "reset_policy": "NEVER", "include_year": False},
        )
    ).json()
    kind = await create_type(client, prefix, policy={"approval_required": False})
    issued = await _issue(client, prefix, kind["revision_id"], series["id"])
    assert issued.status_code == 200, issued.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            counter = await db.scalar(
                select(m.VoucherNumberCounter).where(
                    m.VoucherNumberCounter.series_id == uuid.UUID(series["id"])
                )
            )
            assert counter is not None
            assert counter.fiscal_start_date == dt.date(1000, 1, 1)


async def test_financial_year_series_restarts_at_configured_start(client, prefix):
    today = dt.date.today()
    current_start = dt.date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    prior_end = current_start - dt.timedelta(days=1)
    kind = await create_type(client, prefix, policy={"approval_required": False})
    series = (
        await client.post(
            prefix + "/voucher-series",
            headers=headers(),
            json={"code": "FYRESET", "prefix": "FY-", "start_value": 8, "padding": 3},
        )
    ).json()
    results = []
    for date in (prior_end, current_start):
        voucher, _ = await draft(
            client, prefix, kind["revision_id"], document_date=date.isoformat()
        )
        result = await client.post(
            prefix + f"/vouchers/{voucher['id']}/issue",
            headers=headers(),
            json={"expected_version": 1, "series_id": series["id"]},
        )
        assert result.status_code == 200, result.text
        results.append(result.json()["issue_number"])
    assert results == [
        f"FY-{current_start.year - 1}/008",
        f"FY-{current_start.year}/008",
    ]
