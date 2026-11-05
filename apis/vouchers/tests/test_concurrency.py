import asyncio

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from conftest import TENANT, headers
from sqlalchemy import func, select
from test_foundation import create_type, draft

from vouchers.models import core as m


@pytest.mark.mysql
async def test_native_duplicate_revision_and_numbering_races(client, prefix, app, engine):
    if engine.dialect.name != "mysql":
        pytest.skip("native row-lock test runs through tools/verify_mysql.py")
    kind = await create_type(
        client, prefix, policy={"approval_required": False, "self_approval_allowed": True}
    )
    first, body = await draft(client, prefix, kind["revision_id"])

    async def edit(note):
        return await client.put(
            prefix + "/vouchers/" + first["id"],
            headers=headers(),
            json={"expected_version": 1, "content": body | {"narration": note}},
        )

    replies = await asyncio.gather(edit("A"), edit("B"))
    assert sorted(reply.status_code for reply in replies) == [200, 409]
    series = (
        await client.post(
            prefix + "/voucher-series",
            headers=headers(),
            json={"code": "YEAR", "prefix": "DOC-", "padding": 5},
        )
    ).json()
    second, _ = await draft(client, prefix, kind["revision_id"])
    third, _ = await draft(client, prefix, kind["revision_id"])

    async def issue(voucher, key):
        return await client.post(
            prefix + "/vouchers/" + voucher["id"] + "/issue",
            headers=key,
            json={"expected_version": 1, "series_id": series["id"]},
        )

    retry = headers()
    replies = await asyncio.gather(
        issue(second, retry), issue(second, retry), issue(third, headers())
    )
    assert all(reply.status_code == 200 for reply in replies), [reply.text for reply in replies]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            numbers = list(
                await db.scalars(
                    select(m.VoucherNumberAssignment.sequence).order_by(
                        m.VoucherNumberAssignment.sequence
                    )
                )
            )
            assert numbers == [1, 2]
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "vouchers.voucher.issue"
                    )
                )
                == 2
            )
