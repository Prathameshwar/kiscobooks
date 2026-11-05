"""Apply a reviewed count delta once; current quantity is never overwritten."""

from fractions import Fraction

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import or_, select
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockItemFact, StockWarehouseFact

from accounting.api.auth import Access
from accounting.domain.stock_counting import surplus_value
from accounting.models.stock import StockPosting
from accounting.models.stock_count import StockCountApplication, StockCountObservation
from accounting.tasks.stock_counts import cost_evidence, latest, quantities, require_access
from accounting.tasks.stock_ledger import Leg, StockLedger
from accounting.tasks.stock_ordering import generation


async def apply(
    ledger: StockLedger,
    current: Access,
    line: StockLine,
    item: StockItemFact,
    warehouse: StockWarehouseFact,
) -> Leg | None:
    require_access(current, write=True)
    capture = line.count
    if capture is None or item.serial_tracking:
        raise ConflictError("count requires its native non-serial observation")
    row = await company_object(
        ledger.db,
        StockCountObservation,
        capture.observation_id,
        company_id=ledger.posting.company_id,
    )
    newest = await latest(ledger.db, current, row.root_id)
    if newest.id != row.id or row.revision != capture.expected_revision:
        raise ConflictError("count observation changed; reload the latest revision")
    if row.observed_quantity is None:
        raise ConflictError("an uncounted position cannot be approved as counted zero")
    if any(
        getattr(row, key) != getattr(item, key)
        for key in ("base_unit_id", "quantity_increment", "quantity_decimal_places")
    ):
        raise ConflictError("count base unit rules changed; start a new protected count")
    if any(
        getattr(row, key) != getattr(line, key)
        for key in ("item_id", "warehouse_id", "bin_id", "lot_id")
    ):
        raise ConflictError("count observation belongs to a different physical position")
    if (
        row.observed_quantity != line.quantity
        or row.quantity_entry
        != (line.quantity_entry.model_dump(mode="json") if line.quantity_entry else None)
        or ledger.posting.stock_date < row.stock_date
    ):
        raise ConflictError("stock capture differs from its immutable count observation")
    value = Fraction(line.quantity)
    if (value * 10**item.quantity_decimal_places).denominator != 1 or (
        value / Fraction(item.quantity_increment)
    ).denominator != 1:
        raise ValidationFailedError("count observation violates its native base quantity grid")
    if await ledger.db.scalar(
        select(StockCountApplication.id).where(
            StockCountApplication.company_id == row.company_id,
            StockCountApplication.root_id == row.root_id,
        )
    ):
        raise ConflictError("this physical count variance was already applied")
    ordinal = generation(StockPosting)
    overlapping = await ledger.db.scalar(
        select(StockCountApplication.id)
        .join(
            StockCountObservation, StockCountObservation.id == StockCountApplication.observation_id
        )
        .join(StockPosting, StockPosting.id == StockCountApplication.posting_id)
        .where(
            StockCountApplication.company_id == row.company_id,
            StockCountObservation.company_id == row.company_id,
            StockPosting.company_id == row.company_id,
            *[
                getattr(StockCountObservation, key).is_(None)
                if getattr(row, key) is None
                else getattr(StockCountObservation, key) == getattr(row, key)
                for key in ("item_id", "warehouse_id", "bin_id", "lot_id")
            ],
            or_(ordinal > row.cutoff_generation, ordinal.is_(None)),
        )
        .limit(1)
    )
    if overlapping:
        raise ConflictError("a later count already corrected this cutoff; start a new count")
    book, later, actual = await quantities(ledger.db, row.company_id, row, row.cutoff_generation)
    if book != row.book_quantity:
        raise ConflictError("native count cutoff no longer agrees with protected movement history")
    delta = row.observed_quantity - book
    if actual + delta < 0:
        raise ConflictError("later movements leave insufficient stock for the count shortage")
    ledger.observe(row)
    adjustment = line.model_copy(
        update={"quantity": abs(delta), "quantity_entry": None, "count": None}
    )
    leg = None
    if delta > 0:
        pool, cost = await cost_evidence(ledger.db, row.company_id, row)
        if row.reviewed_unit_cost is not None:
            current.actor.require_scope(
                "accounting.stock.configure", target=ScopePath(company_id=row.company_id)
            )
            if (row.reviewed_pool_id, row.reviewed_pool_version) != (
                pool.id if pool else None,
                pool.row_version if pool else None,
            ):
                raise ConflictError(
                    "native cost changed after review; record a new reviewed observation"
                )
            cost = Fraction(row.reviewed_unit_cost)
        if cost is None:
            raise ConflictError(
                "count surplus requires explicit cost review: "
                "native cost is missing or FIFO costs differ"
            )
        carrying = surplus_value(delta, cost, ledger.places, ledger.rounding)
        leg = await ledger.receive(adjustment, item, warehouse, value=carrying)
    elif delta < 0:
        leg = await ledger.issue(adjustment, item, warehouse, count_adjustment=True)
    ledger.add(
        StockCountApplication,
        root_id=row.root_id,
        observation_id=row.id,
        posting_id=ledger.posting.id,
        difference=delta,
        later_quantity=later,
    )
    await ledger.db.flush()
    return leg
