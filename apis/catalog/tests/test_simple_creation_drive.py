"""The bounded fast path reuses durable single-step advancement."""

from types import SimpleNamespace

from billing_platform.ids import uuid7

from catalog.tasks import simple_product_creation as creation


async def test_drive_finishes_no_opening_without_another_browser_roundtrip(monkeypatch):
    company, identity = uuid7(), uuid7()
    states = [
        SimpleNamespace(status="RUNNING", step="CREATE", row_version=1),
        SimpleNamespace(status="RUNNING", step="ACTIVATE", row_version=2),
        SimpleNamespace(status="COMPLETE", step="COMPLETE", row_version=3),
    ]
    calls = []

    async def read(*args):
        return states[0]

    async def advance(*args):
        calls.append(args)
        return states[len(calls)]

    monkeypatch.setattr(creation, "read", read)
    monkeypatch.setattr(creation, "advance", advance)
    result = await creation.drive(None, None, SimpleNamespace(company_id=company), identity, None)
    assert result.status == "COMPLETE"
    assert len(calls) == 2


async def test_drive_does_not_spin_on_pending_posting(monkeypatch):
    pending = SimpleNamespace(status="RUNNING", step="FINALIZE", row_version=5)
    calls = []

    async def read(*args):
        return pending

    async def advance(*args):
        calls.append(args)
        return pending

    monkeypatch.setattr(creation, "read", read)
    monkeypatch.setattr(creation, "advance", advance)
    result = await creation.drive(
        None, None, SimpleNamespace(company_id=uuid7()), uuid7(), None
    )
    assert result is pending
    assert len(calls) == 1
