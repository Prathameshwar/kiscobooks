"""The tax impact review worker defers failures, detects staleness and resumes durably."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.classification import CatalogPolicyState
from catalog.models.tax_governance import TaxImpactReview
from catalog.tasks import tax_review_worker
from catalog.tasks.identity_source import IdentitySourceSettings, IdentitySourceUnavailableError
from catalog.tasks.tax_impact_reviews import chunk, finish
from tests.bulk_factories import proofs
from tests.conftest import ACTOR_SECRET
from tests.tax_factories import seed_tax
from tests.test_tax_impact_review import add_items, events, release, start

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")
Snapshot = tuple[str, str | None, int, uuid.UUID | None, int]


def worker_settings(
    tenant: uuid.UUID, company: uuid.UUID, *, chunk_size: int
) -> tax_review_worker.TaxReviewWorkerSettings:
    return tax_review_worker.TaxReviewWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=IdentitySourceSettings(
            base_url="http://127.0.0.1:1",
            request_secret=SecretStr(ACTOR_SECRET),
            response_secrets={"current": SecretStr(ACTOR_SECRET)},
        ),
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
        tax_review_chunk_size=chunk_size,
    )


async def issued(_: Any, **kwargs: Any) -> Any:
    """A healthy Identity source: the current proof for exactly the requested chunk."""
    current = proofs(kwargs["tenant_id"], kwargs["company_id"], kwargs["user_id"])
    return next(proof for proof in current if proof.permissions == kwargs["permissions"])


async def snapshot(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, review_id: uuid.UUID
) -> Snapshot:
    with tenant_scope(tenant):
        async with factory() as db:
            row = await db.get(TaxImpactReview, review_id)
            assert row is not None
            return row.status, row.reason_code, row.row_version, row.checkpoint_id, row.item_count


async def set_generation(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, generation: int
) -> int:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            state = await db.scalar(select(CatalogPolicyState))
            assert state is not None
            previous, state.generation = state.generation, generation
            return previous


async def test_worker_defers_proof_and_chunk_failures_then_resumes_from_its_checkpoint(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await add_items(factory, tenant_a, ids, 6)
    review_id = uuid.UUID((await start(client, root, auth, release(ids)))["id"])
    settings = worker_settings(tenant_a, company, chunk_size=4)
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    pending = await snapshot(factory, tenant_a, review_id)
    assert pending[0] == "PENDING" and pending[3] is None
    recorded = await events(factory, tenant_a)

    # Identity cannot verify the requester: nothing is decided, nothing is written.
    async def unavailable(_: Any, **kwargs: Any) -> Any:
        raise IdentitySourceUnavailableError("current actor authorization could not be verified")

    monkeypatch.setattr(tax_review_worker, "fetch_actor_authorization", unavailable)
    assert await tax_review_worker.run_once(factory, settings, cursors) == 0
    assert await snapshot(factory, tenant_a, review_id) == pending
    assert await events(factory, tenant_a) == recorded

    # The chunk does its work and then the transaction fails: every write, including the
    # checkpoint and its chunk audit event, rolls back together.
    monkeypatch.setattr(tax_review_worker, "fetch_actor_authorization", issued)
    original = chunk

    async def broken(*args: Any, **kwargs: Any) -> Any:
        advanced = await original(*args, **kwargs)
        assert advanced.checkpoint_id is not None
        raise RuntimeError("database connection lost")

    monkeypatch.setattr(tax_review_worker, "chunk", broken)
    assert await tax_review_worker.run_once(factory, settings, cursors) == 0
    assert await snapshot(factory, tenant_a, review_id) == pending
    assert await events(factory, tenant_a) == recorded

    # Recovery resumes from the durable checkpoint, not from the in-memory cursor.
    monkeypatch.setattr(tax_review_worker, "chunk", original)
    cursors.clear()
    assert await tax_review_worker.run_once(factory, settings, cursors) == 1
    status, _, version, checkpoint, count = await snapshot(factory, tenant_a, review_id)
    assert (status, version, count) == ("PENDING", pending[2] + 1, 4)
    assert checkpoint is not None
    assert await tax_review_worker.run_once(factory, settings, cursors) == 1
    status, reason, _, last, count = await snapshot(factory, tenant_a, review_id)
    assert (status, reason, count) == ("COMPLETE", None, 7)
    assert last is not None and last > checkpoint
    # Exactly two chunk events: the failed attempt left no audit row behind.
    assert await events(factory, tenant_a) == [
        *recorded,
        "catalog.tax_impact_review.chunk",
        "catalog.tax_impact_review.chunk",
    ]
    assert await tax_review_worker.run_once(factory, settings, cursors) == 0
    assert cursors == {}


async def test_worker_round_robins_marks_stale_and_skips_concurrently_finished_reviews(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await add_items(factory, tenant_a, ids, 2)
    first = uuid.UUID((await start(client, root, auth, release(ids)))["id"])
    second = uuid.UUID(
        (await start(client, root, auth, {**release(ids), "change_reason": "Second"}))["id"]
    )
    assert first < second
    settings = worker_settings(tenant_a, company, chunk_size=2)
    monkeypatch.setattr(tax_review_worker, "fetch_actor_authorization", issued)
    cursors: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    scope = tenant_a, company

    # One chunk per traversal, alternating so neither review starves the other.
    assert await tax_review_worker.run_once(factory, settings, cursors) == 1
    assert cursors[scope] == first
    assert (await snapshot(factory, tenant_a, first))[4] == 2
    assert await tax_review_worker.run_once(factory, settings, cursors) == 1
    assert cursors[scope] == second
    assert (await snapshot(factory, tenant_a, first))[4] == 2
    assert (await snapshot(factory, tenant_a, second))[4] == 2
    # The cursor wraps back to the oldest pending review, which then completes.
    assert await tax_review_worker.run_once(factory, settings, cursors) == 1
    assert cursors[scope] == first
    assert (await snapshot(factory, tenant_a, first))[0::4] == ("COMPLETE", 3)

    # A policy change while a review is still running invalidates it on its next chunk.
    original_generation = await set_generation(factory, tenant_a, 7)
    assert await tax_review_worker.run_once(factory, settings, cursors) == 1
    stale = await snapshot(factory, tenant_a, second)
    assert stale[:2] == ("STALE", "policy_changed") and stale[4] == 2
    assert "catalog.tax_impact_review.stale" in await events(factory, tenant_a)

    # A review that leaves PENDING between selection and its chunk is skipped untouched,
    # and is never re-labelled as failed.
    await set_generation(factory, tenant_a, original_generation)
    third = uuid.UUID(
        (await start(client, root, auth, {**release(ids), "change_reason": "Third"}))["id"]
    )

    async def finished_meanwhile(settings_: Any, **kwargs: Any) -> Any:
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                row = await db.get(TaxImpactReview, third)
                assert row is not None
                if row.status == "PENDING":
                    finish(row, "STALE", "policy_changed")
        return await issued(settings_, **kwargs)

    monkeypatch.setattr(tax_review_worker, "fetch_actor_authorization", finished_meanwhile)
    before = await events(factory, tenant_a)
    assert await tax_review_worker.run_once(factory, settings, cursors) == 0
    assert (await snapshot(factory, tenant_a, third))[:2] == ("STALE", "policy_changed")
    assert await events(factory, tenant_a) == before


async def test_serve_survives_a_failed_traversal_polls_when_idle_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = worker_settings(uuid.uuid4(), uuid.uuid4(), chunk_size=4)
    calls: list[str] = []

    class Engine:
        async def dispose(self) -> None:
            calls.append("dispose")

    engine = Engine()
    factory = object()

    def create_engine(url: str) -> Engine:
        assert url == settings.database_url
        return engine

    def create_session_factory(bound: Engine, *, guarded: bool) -> object:
        assert bound is engine and guarded
        return factory

    outcomes: list[Any] = [RuntimeError("database unavailable"), 1, 0]

    async def run_once(used: Any, given: Any, cursors: dict[Any, Any]) -> int:
        assert used is factory and given is settings
        calls.append("run")
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return int(outcome)

    class StopServingError(Exception):
        pass

    async def sleep(seconds: int) -> None:
        assert seconds == settings.tax_review_poll_seconds
        calls.append("sleep")
        if not outcomes:
            raise StopServingError

    monkeypatch.setattr(tax_review_worker, "create_engine", create_engine)
    monkeypatch.setattr(tax_review_worker, "create_session_factory", create_session_factory)
    monkeypatch.setattr(tax_review_worker, "run_once", run_once)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(StopServingError):
        await tax_review_worker.serve(settings)
    # A failed traversal sleeps like an idle one; productive traversals continue at once.
    assert calls == ["run", "sleep", "run", "run", "sleep", "dispose"]


def test_main_serves_settings_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    served: list[object] = []

    async def serve(settings: object) -> None:
        served.append(settings)

    monkeypatch.setattr(tax_review_worker, "TaxReviewWorkerSettings", lambda: sentinel)
    monkeypatch.setattr(tax_review_worker, "serve", serve)
    tax_review_worker.main()
    assert served == [sentinel]
