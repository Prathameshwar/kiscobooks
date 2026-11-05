"""A download re-checks every label the frozen PDF carries, not only the calculation.

Names and the voucher number come back from Accounting only while the actor may still read them.
A read denied since generation must stop the old PDF, which still prints those names.
"""

import copy
import hashlib
import uuid

import pytest
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from test_purchase_print import queued, snapshot

from vouchers.tasks import print_worker, purchase_print

REAL_REAUTHORIZE = purchase_print.reauthorize
CHANGED = "Purchase print details changed or are no longer readable; generate a fresh copy"
PRIVATE = ("Example Supplier", "Renamed Supplier", "Purchases", "Another ledger", "PUR/26-27")


def frozen():
    """A posted bill's frozen snapshot that carries every label."""
    value = snapshot()
    line = value["document"]["invoice"]["supplies"][0]["line_key"]
    value["document"]["revision_id"] = str(uuid7())
    value["calculation_source"] = "POSTED"
    value["labels"] = {
        "supplier": "Example Supplier",
        "voucher_number": "PUR/26-27/00042",
        "ledgers": {line: "Purchases"},
    }
    return value, line


def with_labels(value, **labels):
    latest = copy.deepcopy(value)
    latest["labels"] = latest["labels"] | labels
    return latest


async def reauthorize_against(monkeypatch, latest, value):
    """Run the real re-authorization with ``latest`` as what Accounting returns today."""

    async def prepare(*args, **kwargs):
        return copy.deepcopy(latest)

    monkeypatch.setattr(purchase_print, "prepare", prepare)
    await REAL_REAUTHORIZE(None, None, uuid7(), value)


async def test_unchanged_labels_are_allowed(monkeypatch):
    value, _ = frozen()
    await reauthorize_against(monkeypatch, value, value)


@pytest.mark.parametrize(
    "change",
    [
        lambda line: {"supplier": None},
        lambda line: {"supplier": "Renamed Supplier"},
        lambda line: {"voucher_number": None},
        lambda line: {"voucher_number": "PUR/26-27/00099"},
        lambda line: {"ledgers": {line: None}},
        lambda line: {"ledgers": {line: "Another ledger"}},
        lambda line: {"ledgers": {}},
    ],
)
async def test_a_label_now_missing_or_different_is_refused(monkeypatch, change):
    value, line = frozen()
    with pytest.raises(ConflictError) as refused:
        await reauthorize_against(monkeypatch, with_labels(value, **change(line)), value)
    message = str(refused.value)
    assert CHANGED in message
    assert not any(private in message for private in PRIVATE)


async def test_a_calculation_change_is_still_refused(monkeypatch):
    value, _ = frozen()
    latest = copy.deepcopy(value)
    latest["calculation"]["calculation_hash"] = "c" * 64
    with pytest.raises(ConflictError) as refused:
        await reauthorize_against(monkeypatch, latest, value)
    assert "calculation changed" in str(refused.value)


async def test_labels_restricted_at_creation_stay_allowed_while_still_restricted(monkeypatch):
    value, line = frozen()
    value["calculation_source"] = "PREVIEW"
    value["labels"] = {"supplier": None, "voucher_number": None, "ledgers": {line: None}}
    await reauthorize_against(monkeypatch, value, value)
    # The frozen copy prints no name, so a name that has become readable discloses nothing new.
    readable = with_labels(value, supplier="Example Supplier", ledgers={line: "Purchases"})
    await reauthorize_against(monkeypatch, readable, value)
    # A snapshot that carries no label at all behaves the same way.
    bare = copy.deepcopy(value)
    bare["labels"] = {}
    await reauthorize_against(monkeypatch, value, bare)


def test_labels_unchanged_is_a_pure_comparison():
    from vouchers.domain.purchase_print import labels_unchanged

    line = str(uuid.uuid4())
    held = {"supplier": "S", "voucher_number": "N", "ledgers": {line: "L"}}
    assert labels_unchanged(held, dict(held))
    assert labels_unchanged({}, {})
    assert labels_unchanged({"supplier": None, "ledgers": {line: None}}, {})
    assert not labels_unchanged(held, held | {"supplier": None})
    assert not labels_unchanged(held, held | {"voucher_number": "M"})
    assert not labels_unchanged(held, held | {"ledgers": {}})
    assert not labels_unchanged(held, {"supplier": "S", "voucher_number": "N"})


async def test_download_is_refused_when_a_label_is_no_longer_readable(
    client, prefix, app, tmp_path, monkeypatch
):
    saved, _, value, url, body = await queued(client, prefix, app, tmp_path, monkeypatch)
    value["document"]["revision_id"] = saved["revision_id"]
    created = await client.post(url, json=body, headers=headers())
    assert created.status_code == 202, created.text
    identity = created.json()["id"]
    data = b"%PDF-1.7\nVerified test renderer\n%%EOF"
    monkeypatch.setattr(print_worker, "render", lambda settings, snapshot_value: data)
    await print_worker.execute(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, uuid.UUID(identity)
    )
    status_url = prefix + "/voucher-print-jobs/" + identity
    status = (await client.get(status_url, headers=headers())).json()
    assert status["status"] == "READY"
    assert status["content_hash"] == hashlib.sha256(data).hexdigest()
    download, token = status_url + "/download", {"token": status["download_token"]}
    # From here the real re-authorization runs against what Accounting returns today.
    monkeypatch.setattr(purchase_print, "reauthorize", REAL_REAUTHORIZE)

    def owner_returns(supplier):
        async def prepare(*args, **kwargs):
            return with_labels(value, supplier=supplier)

        monkeypatch.setattr(purchase_print, "prepare", prepare)

    owner_returns("Example Supplier")
    ok = await client.get(download, params=token, headers=headers())
    assert ok.status_code == 200 and ok.content == data
    owner_returns(None)
    refused = await client.get(download, params=token, headers=headers())
    assert refused.status_code == 409, refused.text
    assert CHANGED in refused.json()["error"]["message"]
    assert "Example Supplier" not in refused.text
