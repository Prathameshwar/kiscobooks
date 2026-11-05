"""Signed source version/replay/closure and owner-isolation regressions."""

import copy
import datetime as dt

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT
from sqlalchemy import select
from test_sources_custom_artifacts import source
from unit_source_factories import unit_masters

from vouchers.models.unit_sources import VoucherItemUnitProjection


async def test_signed_unit_history_is_owner_scoped_and_immutable(client, app):
    masters = unit_masters(uuid7(), uuid7())
    denied = await source(client, app, issuer="accounting", masters=masters)
    assert denied.status_code == 422
    message = uuid7()
    applied = await source(client, app, issuer="catalog", masters=masters, message_id=message)
    assert applied.status_code == 200, applied.text
    replay = await source(client, app, issuer="catalog", masters=masters, message_id=message)
    assert replay.status_code == 200 and replay.json()["replayed"]
    updated = copy.deepcopy(masters[2])
    updated["source_version"] = 2
    updated["facts"]["quantity_increment"] = "2"
    rejected = await source(client, app, issuer="catalog", masters=[updated])
    assert rejected.status_code == 409
    updated["facts"]["quantity_increment"] = "0.0001"
    updated["facts"]["valid_to"] = "2026-10-30"
    closed = await source(client, app, issuer="catalog", masters=[updated])
    assert closed.status_code == 200, closed.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.scalar(
                select(VoucherItemUnitProjection).where(
                    VoucherItemUnitProjection.company_id == COMPANY
                )
            )
            assert row.valid_to == dt.date(2026, 10, 30)
            assert row.source_version == 2


async def test_old_empty_item_and_unit_facts_upgrade_once(client, app):
    masters = unit_masters(uuid7(), uuid7())
    old = [{**row, "facts": {}} for row in masters[:2]]
    assert (await source(client, app, issuer="catalog", masters=old)).status_code == 200
    new = await source(client, app, issuer="catalog", masters=masters)
    assert new.status_code == 200, new.text
    changed = copy.deepcopy(masters[1])
    changed["facts"]["quantity_increment"] = "1"
    assert (await source(client, app, issuer="catalog", masters=[changed])).status_code == 409
