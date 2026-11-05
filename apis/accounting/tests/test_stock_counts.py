"""Native count execution reconciles quantity, value and its real posted journal."""

import datetime as dt
import hashlib
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.transport import command_digest

from accounting.api.auth import delegated_access
from accounting.models.ledger import Journal
from accounting.models.stock import StockBalance, StockCostPool, StockPosting, StockReceiptOrigin
from accounting.models.stock_count import StockCountApplication, StockCountObservation
from accounting.schemas.stock_count import CountObservationInput, CountScope
from accounting.tasks.stock_counts import create_local, observe
from accounting.tasks.stock_execution import _dispatch, dispatch
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_stock_effects import Source, authority, captured, configure, source
from tests.test_stock_ledger import item, warehouse


def current(request):
    return delegated_access(
        request.authority,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=request.actor_user_id,
    )


async def post(app, owner, request, product, location):
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    return result


async def count(app, request, product, location, observed, *, key="count", cost=None):
    scope = CountScope(
        item_id=product.item_id,
        warehouse_id=location.warehouse_id,
        stock_date=request.stock_date,
        reason="Controlled native physical count",
    )
    with tenant_scope(TENANT):
        started = await create_local(
            app.state.session_factory,
            current(request),
            scope,
            key,
            source(request, product, location),
        )
        assert started.value.status == "UNCOUNTED" and started.value.observed_quantity is None
        recorded = await observe(
            app.state.session_factory,
            current(request),
            started.value.id,
            CountObservationInput(
                expected_revision=1,
                observed_quantity=observed,
                reason="Reviewed physical observation",
                reviewed_unit_cost=cost,
                cost_review_reason="Reviewed verified cost evidence" if cost is not None else None,
            ),
            key + "-observe",
        )
    return recorded.value


def count_request(period, product, location, observation):
    request = captured(period, product, location)
    stock = request.source_payload["stock"]
    line = {
        key: value
        for key, value in stock["lines"][0].items()
        if key not in {"received_value", "zero_value_reason"}
    }
    line.update(
        quantity=str(observation.observed_quantity),
        count={"observation_id": str(observation.id), "expected_revision": observation.revision},
    )
    day = str(observation.stock_date)
    payload = request.source_payload | {
        "stock": stock | {"action": "COUNT", "stock_date": day, "lines": [line]},
        "posting_date": day,
        "stock_date": day,
        "document_date": day,
        "lines": [
            {
                "line_key": line["line_id"],
                "item": request.source_payload["lines"][0]["item"]
                | {"actual_quantity": str(observation.observed_quantity)},
            }
        ],
    }
    evidence = request.configuration_evidence | {"kind": "PHYSICAL_STOCK"}
    evidence.pop("digest")
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    request = request.model_copy(
        update={
            "kind": "PHYSICAL_STOCK",
            "posting_date": observation.stock_date,
            "stock_date": observation.stock_date,
            "source_payload": payload,
            "configuration_evidence": evidence | {"digest": digest},
            "configuration_hash": digest,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
        }
    )
    return request.model_copy(update={"request_hash": command_digest(request)})


@pytest.mark.parametrize(
    "observed,expected_quantity,expected_value",
    [
        ("1", "3", "18.75"),
        ("0", "2", "12.50"),
        ("3", "5", "31.25"),
        ("2", "4", "25.00"),
    ],
)
async def test_cutoff_preserves_later_movements_and_posts_variance_once(
    app, client, observed, expected_quantity, expected_value
):
    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = (
        item(),
        warehouse().model_copy(
            update={"allowed_operations": (*warehouse().allowed_operations, "ADJUSTMENT")}
        ),
    )
    first = captured(period, product, location)
    await post(app, owner, first, product, location)
    observation = await count(app, first, product, location, observed)
    assert observation.book_quantity == 2 and observation.difference == Decimal(observed) - 2
    await post(app, owner, captured(period, product, location), product, location)
    request = count_request(period, product, location, observation)
    result = await post(app, owner, request, product, location)
    replay = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=None,
        enabled=True,
    )
    assert replay == result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(StockBalance.quantity)) == Decimal(expected_quantity)
            pool = await db.scalar(select(StockCostPool))
            assert pool.value == Decimal(expected_value)
            claim = await db.scalar(select(StockCountApplication))
            assert claim.difference == Decimal(observed) - 2 and claim.later_quantity == 2
            assert await db.scalar(select(func.count(StockCountApplication.id))) == 1
            assert await db.scalar(select(func.count(StockCountObservation.id))) == 2
            count_posting = await db.scalar(
                select(StockPosting).where(StockPosting.action == "COUNT")
            )
            if observed == "2":
                assert count_posting.journal_id is None
            else:
                journal = await db.get(Journal, count_posting.journal_id)
                assert journal.status == "POSTED" and journal.total_debit == abs(
                    Decimal(observed) - 2
                ) * Decimal("6.25")


async def test_mixed_fifo_cost_requires_review_and_recount_invalidates_old_capture(app, client):
    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = (
        item(),
        warehouse().model_copy(
            update={"allowed_operations": (*warehouse().allowed_operations, "ADJUSTMENT")}
        ),
    )
    first = captured(period, product, location, amount="10")
    await post(app, owner, first, product, location)
    await post(app, owner, captured(period, product, location, amount="20"), product, location)
    observation = await count(app, first, product, location, "5")
    assert observation.cost_review_required
    request = count_request(period, product, location, observation)
    with pytest.raises(ConflictError, match="cost review"):
        await post(app, owner, request, product, location)
    with tenant_scope(TENANT):
        revised = (
            await observe(
                app.state.session_factory,
                current(first),
                observation.id,
                CountObservationInput(
                    expected_revision=2,
                    observed_quantity="5",
                    reason="Reviewed recount",
                    reviewed_unit_cost="7.50",
                    cost_review_reason="Verified reviewed cost",
                ),
                "mixed-review",
            )
        ).value
    with pytest.raises(ConflictError, match="observation changed"):
        await post(app, owner, request, product, location)
    await post(app, owner, count_request(period, product, location, revised), product, location)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(StockBalance.quantity)) == 5
            assert await db.scalar(select(StockCostPool.value)) == Decimal("37.50")


@pytest.mark.parametrize("observed,quantity,value", [("1", "3", "24.37"), ("3", "5", "40.63")])
async def test_moving_average_uses_current_verified_native_cost(
    app, client, observed, quantity, value
):
    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product = item("MOVING_AVERAGE")
    location = warehouse()
    location = location.model_copy(
        update={"allowed_operations": (*location.allowed_operations, "ADJUSTMENT")}
    )
    first = captured(period, product, location)
    await post(app, owner, first, product, location)
    observation = await count(app, first, product, location, observed)
    await post(app, owner, captured(period, product, location, amount="20"), product, location)
    await post(app, owner, count_request(period, product, location, observation), product, location)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == Decimal(quantity) and pool.value == Decimal(value)


async def test_missing_cost_requires_review_and_count_reversal_preserves_history(app, client):
    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    location = location.model_copy(
        update={"allowed_operations": (*location.allowed_operations, "ADJUSTMENT")}
    )
    first = captured(period, product, location)
    observation = await count(app, first, product, location, "1")
    assert observation.book_quantity == 0 and observation.cost_review_required
    with pytest.raises(ConflictError, match="cost review"):
        await post(
            app, owner, count_request(period, product, location, observation), product, location
        )
    with tenant_scope(TENANT):
        reviewed = (
            await observe(
                app.state.session_factory,
                current(first),
                observation.id,
                CountObservationInput(
                    expected_revision=2,
                    observed_quantity="1",
                    reason="Reviewed found stock",
                    reviewed_unit_cost="5",
                    cost_review_reason="Verified reviewed surplus cost",
                ),
                "missing-cost-review",
            )
        ).value
    request = count_request(period, product, location, reviewed)
    await post(app, owner, request, product, location)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(StockReceiptOrigin))).history_known is False
    reverse = request.model_copy(
        update={
            "purpose": "REVERSE",
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "reversal_of_execution_id": request.execution_id,
            "correction_reason": "Correct the reviewed count",
            "authority": authority(),
            "authority_expires_at": utcnow() + dt.timedelta(seconds=60),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    result = await dispatch(
        app.state.session_factory,
        reverse,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(
            source(reverse, product, location).model_copy(update={"action": "REVERSE"})
        ),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(StockBalance.quantity)) == 0
            assert await db.scalar(select(StockCostPool.value)) == 0
            assert await db.scalar(select(func.count(StockCountApplication.id))) == 1
