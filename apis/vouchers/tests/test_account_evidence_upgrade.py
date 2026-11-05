"""Account evidence replicated before Accounting published ``party_id`` can be repaired (D9).

A bill whose ledger evidence has no ``party_id`` key is refused with "re-synchronise from
Accounting". A re-sync republishes the same ledger at the same version, which used to be a
conflict, so nothing repaired the evidence until the ledger was next edited. One narrow, additive
upgrade is allowed; any other difference at the same version is still a conflict.
"""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from conftest import TENANT, headers
from sqlalchemy import func, select
from test_foundation import create_type
from test_invoice_capture import invoice_body
from test_purchase_lifecycle_integrity import OLD, master, project, request_for, seed

from vouchers.domain.configuration import digest
from vouchers.models import core as m

CONFLICT = "master version has conflicting content"


async def stored(app, entity, source):
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.scalar(
                select(m.VoucherMasterEvidence).where(
                    m.VoucherMasterEvidence.entity_type == entity,
                    m.VoucherMasterEvidence.source_id == source,
                )
            )
            assert row is not None
            return {
                "facts": dict(row.facts),
                "status": row.status,
                "source_version": row.source_version,
                "row_version": row.row_version,
                "content_hash": row.content_hash,
            }


async def applied_events(app):
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            return await db.scalar(
                select(func.count(Outbox.id)).where(Outbox.event_type == "vouchers.source.applied")
            )


async def old_ledger(app, **extra):
    """A ledger projected without a party link, as before Accounting published one."""
    ledger = uuid7()
    await project(app, [master("account", ledger, kind="GENERAL", **extra)])
    return ledger


async def test_a_resync_adds_the_party_link_to_same_version_account_evidence(client, prefix, app):
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=OLD)
    ledger = uuid.UUID(body["party_account_id"])
    request = request_for(kind, body, supplier)
    refused = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert refused.status_code == 422 and "re-synchronise" in refused.json()["error"]["message"]
    before = await stored(app, "account", ledger)
    assert "party_id" not in before["facts"]
    events = await applied_events(app)

    await project(app, [master("account", ledger, kind="GENERAL", party_id=str(supplier))])

    after = await stored(app, "account", ledger)
    assert after["facts"] == {"kind": "GENERAL", "party_id": str(supplier)}
    assert (after["source_version"], after["status"]) == (1, "ACTIVE")
    assert after["row_version"] == before["row_version"] + 1
    assert after["content_hash"] != before["content_hash"]
    assert after["content_hash"] == digest(
        master("account", str(ledger), kind="GENERAL", party_id=str(supplier))
    )
    assert await applied_events(app) == events + 1, "the upgrade is audited like any applied bundle"
    created = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert created.status_code == 201, created.text


async def test_an_account_that_belongs_to_no_party_can_also_be_upgraded(app):
    ledger = await old_ledger(app)
    await project(app, [master("account", ledger, kind="GENERAL", party_id=None)])
    assert (await stored(app, "account", ledger))["facts"] == {"kind": "GENERAL", "party_id": None}


async def test_republishing_the_upgrade_again_changes_nothing(app):
    ledger = await old_ledger(app)
    supplier = str(uuid7())
    await project(app, [master("account", ledger, kind="GENERAL", party_id=supplier)])
    first = await stored(app, "account", ledger)
    await project(app, [master("account", ledger, kind="GENERAL", party_id=supplier)])
    assert await stored(app, "account", ledger) == first


@pytest.mark.parametrize(
    "incoming",
    [
        pytest.param({"kind": "BANK", "party_id": "SUPPLIER"}, id="another-fact-changes"),
        pytest.param({"kind": "GENERAL", "party_id": "SUPPLIER", "name": "x"}, id="extra-fact"),
        pytest.param({"party_id": "SUPPLIER"}, id="fact-removed"),
        pytest.param({"kind": "BANK"}, id="no-link-but-changed"),
    ],
)
async def test_any_other_difference_at_the_same_version_is_still_a_conflict(app, incoming):
    ledger = await old_ledger(app)
    before = await stored(app, "account", ledger)
    facts = {k: (str(uuid7()) if v == "SUPPLIER" else v) for k, v in incoming.items()}
    events = await applied_events(app)
    with pytest.raises(ConflictError, match=CONFLICT):
        await project(app, [master("account", ledger, **facts)])
    assert await stored(app, "account", ledger) == before
    assert await applied_events(app) == events


async def test_a_status_change_is_not_part_of_the_upgrade(app):
    ledger = await old_ledger(app)
    before = await stored(app, "account", ledger)
    retired = master("account", ledger, kind="GENERAL", party_id=str(uuid7())) | {
        "status": "RETIRED"
    }
    with pytest.raises(ConflictError, match=CONFLICT):
        await project(app, [retired])
    assert await stored(app, "account", ledger) == before


@pytest.mark.parametrize("stored_link", [None, "OTHER"], ids=["null-link", "other-party"])
async def test_a_link_that_is_already_recorded_is_never_rewritten(app, stored_link):
    first = str(uuid7()) if stored_link == "OTHER" else None
    ledger = await old_ledger(app, party_id=first)
    before = await stored(app, "account", ledger)
    with pytest.raises(ConflictError, match=CONFLICT):
        await project(app, [master("account", ledger, kind="GENERAL", party_id=str(uuid7()))])
    assert await stored(app, "account", ledger) == before


async def test_only_account_evidence_has_this_upgrade(app):
    party = uuid7()
    await project(app, [master("party", party, kind="SUPPLIER")])
    with pytest.raises(ConflictError, match=CONFLICT):
        await project(app, [master("party", party, kind="SUPPLIER", party_id=str(uuid7()))])
    assert (await stored(app, "party", party))["facts"] == {"kind": "SUPPLIER"}


async def test_a_newer_version_still_replaces_the_evidence_as_before(app):
    ledger = await old_ledger(app)
    newer = master("account", ledger, kind="BANK", party_id=str(uuid7())) | {"source_version": 2}
    await project(app, [newer])
    after = await stored(app, "account", ledger)
    assert after["source_version"] == 2 and after["facts"]["kind"] == "BANK"
