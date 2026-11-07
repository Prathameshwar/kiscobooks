"""Certify complete stock evidence from the native owner under its posting fence.

Catalog masters must come from a live immutable company definition lease. Publication
and coverage are atomic; historical value deltas never stand in for residual costs.
"""

import datetime as dt
import uuid
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from reporting_contract.inventory import (
    CostLayer,
    CostPool,
    Coverage,
    InventoryRecord,
    Origin,
    Position,
    ValuationDetail,
)
from sqlalchemy import JSON, LargeBinary, String, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution import ExecutionCommand, ExecutionResult

from accounting.models.fiscal import FinancialSetup
from accounting.models.inventory_reporting import InventoryReportRecord
from accounting.models.stock import (
    StockBalance,
    StockCostLayer,
    StockCostPool,
    StockMovement,
    StockOriginBalance,
    StockPosition,
    StockPosting,
    StockReceiptOrigin,
    StockUnitPosition,
)
from accounting.models.stock_tracking import StockLot, StockUnit, StockUnitIdentifier
from accounting.models.voucher_execution import VoucherExecution
from accounting.tasks.inventory_reporting import publish
from accounting.tasks.reporting_feed import lock
from accounting.tasks.stock_reconciliation import assert_physical
from accounting.tasks.stock_unit_reconciliation import assert_units


async def recover_committed_movements(
    db: AsyncSession,
    *,
    company: uuid.UUID,
    postings: dict[uuid.UUID, StockPosting],
    movements: list[StockMovement],
    reported: set[uuid.UUID],
) -> None:
    """Restore missing report rows only from retained, committed owner executions.

    Older goods bills lacked a pre-issued number. Their posted journal is the number
    authority. Legacy stock without either number remains explicitly incomplete.
    """
    missing = {row.posting_id for row in movements if row.id not in reported}
    if not missing:
        return
    execution_ids = {postings[key].execution_id for key in missing if key in postings}
    if not execution_ids:
        return
    receipts = list(
        await db.scalars(
            select(VoucherExecution).where(
                VoucherExecution.company_id == company,
                VoucherExecution.execution_id.in_(execution_ids),
            )
        )
    )
    from accounting.tasks.stock_reporting import capture

    for receipt in receipts:
        command = ExecutionCommand.model_validate(receipt.command)
        result = ExecutionResult.model_validate(receipt.result)
        if command.company_id != company or result.outcome != "COMMITTED":
            continue
        await capture(db, command, result)
    await db.flush()


def source_id(company: uuid.UUID, kind: str, identity: object = "complete") -> uuid.UUID:
    return uuid.uuid5(company, "native-stock-summary:" + kind + ":" + str(identity))


async def bounded(db: AsyncSession, model: Any, company: uuid.UUID) -> list[Any]:
    width = literal(512) + func.length(cast(model.id, LargeBinary))
    for column in model.__table__.columns:
        if isinstance(column.type, JSON | String | LargeBinary):
            width = width + func.coalesce(
                func.length(cast(getattr(model, column.key), LargeBinary)), 0
            )
    size = await db.scalar(
        select(func.coalesce(func.sum(width), 0)).where(model.company_id == company)
    )
    if size is None or size > 16 * 1024 * 1024:
        raise ConflictError("stock snapshot exceeds its native source memory bound")
    records = list(await db.scalars(select(model).where(model.company_id == company).limit(100001)))
    if len(records) > 100000:
        raise ConflictError("stock snapshot exceeds its negotiated native capacity")
    return records


async def publish_complete(
    db: AsyncSession,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    as_of: dt.date,
    masters: list[dict[str, Any]],
    policy_hash: str,
) -> None:
    await db.run_sync(lambda sync: lock(sync, company))
    setup = await db.scalar(select(FinancialSetup).where(FinancialSetup.company_id == company))
    if setup is None or setup.tenant_id != tenant or as_of < setup.books_begin_date:
        raise ConflictError("initialized company financial coverage is required for stock")
    await assert_physical(db, company)
    await assert_units(db, company)
    typed = [InventoryRecord.model_validate({"payload": value}).payload for value in masters]
    kinds: dict[str, list[Any]] = defaultdict(list)
    records: list[tuple[uuid.UUID, dict[str, Any]]] = []
    for master in typed:
        if master.kind not in {"ITEM", "LOCATION", "GROUP"}:
            raise ConflictError("Catalog may supply only stock master definitions")
        identity = getattr(
            master, {"ITEM": "item_id", "LOCATION": "location_id", "GROUP": "group_id"}[master.kind]
        )
        records.append(
            (source_id(company, master.kind, identity), {"payload": master.model_dump(mode="json")})
        )
        kinds[master.kind].append(master)
    items = {r.item_id: r for r in kinds["ITEM"]}
    locations = {r.location_id: r for r in kinds["LOCATION"]}
    if len(items) != len(kinds["ITEM"]) or len(locations) != len(kinds["LOCATION"]):
        raise ConflictError("stock master snapshot repeats an identity")
    positions = await bounded(db, StockPosition, company)
    balances = {r.position_id: r for r in await bounded(db, StockBalance, company)}
    pools = {(r.item_id, r.warehouse_id): r for r in await bounded(db, StockCostPool, company)}
    layers: dict[uuid.UUID, list[Any]] = defaultdict(list)
    for layer in await bounded(db, StockCostLayer, company):
        if layer.remaining_quantity > 0:
            layers[layer.pool_id].append(layer)
    origins = {r.id: r for r in await bounded(db, StockReceiptOrigin, company)}
    origin_balances: dict[uuid.UUID, list[Any]] = defaultdict(list)
    for balance in await bounded(db, StockOriginBalance, company):
        if balance.quantity > 0:
            origin_balances[balance.position_id].append(balance)
    origins_complete = all(len(rows) <= 200 for rows in origin_balances.values())
    postings = {r.id: r for r in await bounded(db, StockPosting, company)}
    movements = await bounded(db, StockMovement, company)
    lots = {r.id: r for r in await bounded(db, StockLot, company)}
    units = {r.id: r for r in await bounded(db, StockUnit, company)}
    identifiers: dict[uuid.UUID, list[Any]] = defaultdict(list)
    for identifier in await bounded(db, StockUnitIdentifier, company):
        identifiers[identifier.unit_id].append(identifier)
    serials: dict[uuid.UUID, list[str]] = defaultdict(list)
    held_units: dict[uuid.UUID, int] = defaultdict(int)
    for unit_position in await bounded(db, StockUnitPosition, company):
        unit = units.get(unit_position.unit_id)
        if unit is None:
            raise ConflictError("native stock serial metadata is unavailable")
        if unit_position.position_id:
            choices = sorted(
                identifiers[unit.id], key=lambda r: (r.identifier_type != "SERIAL", r.slot, r.id)
            )
            if not choices:
                raise ConflictError("native stock unit identifier is unavailable")
            serials[unit_position.position_id].append(choices[0].value)
        if unit_position.position_id and (unit.is_held or unit.status != "ACTIVE"):
            held_units[unit_position.position_id] += 1
    previous = await bounded(db, InventoryReportRecord, company)
    await recover_committed_movements(
        db,
        company=company,
        postings=postings,
        movements=movements,
        reported={row.id for row in previous if row.payload["kind"] == "MOVEMENT"},
    )
    previous = await bounded(db, InventoryReportRecord, company)
    coverage_id = source_id(company, "COVERAGE")
    if any(r.payload["kind"] == "COVERAGE" and r.id != coverage_id for r in previous):
        raise ConflictError("an external inventory source already owns company coverage")
    movement_ids = {r.id for r in movements}
    handed_off = [r for r in previous if r.payload["kind"] == "MOVEMENT"]
    if any(r.id not in movement_ids for r in handed_off):
        raise ConflictError("inventory movement source differs from the native owner")
    if any(
        r.stock_date > as_of or r.stock_date < setup.books_begin_date for r in postings.values()
    ):
        raise ConflictError("native stock dates fall outside this complete current snapshot")
    turnover: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(
        lambda: {"opening": Decimal(0), "inward": Decimal(0), "outward": Decimal(0)}
    )
    pool_positions: dict[tuple[uuid.UUID, uuid.UUID], list[Any]] = defaultdict(list)
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for movement in movements:
            posting = postings.get(movement.posting_id)
            if posting is None:
                raise ConflictError("native stock movement has no retained posting")
            key = (
                "opening"
                if posting.action == "OPENING"
                else "inward"
                if movement.quantity >= 0
                else "outward"
            )
            turnover[movement.position_id][key] += (
                movement.quantity if key == "opening" else abs(movement.quantity)
            )
        for position in positions:
            pool_positions[(position.item_id, position.warehouse_id)].append(position)
        valuation_complete = True
        for native in positions:
            if native.item_id not in items or native.warehouse_id not in locations:
                raise ConflictError(
                    "native stock master is missing from the complete Catalog lease"
                )
            if (
                native.owner_kind != "COMPANY"
                or native.custody_kind not in {"WAREHOUSE", "TRANSIT"}
                or native.disposition != "USABLE"
            ):
                raise ConflictError(
                    "native stock scope requires a supported source ownership contract"
                )
            balance = balances.get(native.id)
            pool = pools.get((native.item_id, native.warehouse_id))
            if balance is None or pool is None or pool.currency != setup.base_currency:
                raise ConflictError("native stock balance or cost pool is unavailable")
            peers = pool_positions[(native.item_id, native.warehouse_id)]
            if (
                sum((balances[r.id].quantity for r in peers if r.id in balances), Decimal(0))
                != pool.quantity
            ):
                raise ConflictError("native warehouse cost pool quantity does not reconcile")
            value = str(pool.value) if len(peers) == 1 else "0" if balance.quantity == 0 else None
            valuation_complete &= value is not None
            lot = lots.get(native.lot_id) if native.lot_id else None
            if native.lot_id and lot is None:
                raise ConflictError("native stock lot metadata is unavailable")
            totals = turnover[native.id]
            residual = []
            if len(origin_balances[native.id]) <= 200:
                for cohort in sorted(
                    origin_balances[native.id], key=lambda row: str(row.origin_id)
                ):
                    origin = origins.get(cohort.origin_id)
                    if origin is None:
                        raise ConflictError("native remaining receipt origin is unavailable")
                    residual.append(
                        Origin(
                            origin_id=origin.id,
                            receipt_date=origin.received_on
                            if origin.history_known is True
                            else None,
                            manufacture_date=lot.manufactured_on if lot else None,
                            provenance="KNOWN" if origin.history_known is True else "UNKNOWN",
                            quantity=str(cohort.quantity),
                        )
                    )
            detail = None
            if len(peers) == 1:
                if pool.method == "MOVING_AVERAGE":
                    detail = ValuationDetail(
                        pool=CostPool(
                            pool_id=pool.id,
                            quantity=str(balance.quantity),
                            carrying_value=str(pool.value),
                        )
                    )
                elif len(layers[pool.id]) <= 200:
                    detail = ValuationDetail(
                        layers=[
                            CostLayer(
                                layer_id=layer.id,
                                receipt_date=layer.received_on,
                                quantity=str(layer.remaining_quantity),
                                carrying_value=str(layer.remaining_value),
                            )
                            for layer in sorted(
                                layers[pool.id], key=lambda row: (row.received_on, str(row.id))
                            )
                        ]
                    )
            position = Position(
                position_id=native.id,
                item_id=native.item_id,
                location_id=native.warehouse_id,
                bin_id=native.bin_id,
                owner="OWN",
                custody="TRANSIT" if native.custody_kind == "TRANSIT" else "LOCAL",
                disposition="HELD" if lot and lot.is_held else "GOOD",
                quantity=str(balance.quantity),
                eligible_quantity=str(
                    balance.quantity - held_units[native.id]
                    if locations[native.warehouse_id].sale_eligible is not False
                    and not locations[native.warehouse_id].is_group
                    and items[native.item_id].active
                    and items[native.item_id].sale_location_permissions.get(
                        native.warehouse_id,
                        items[native.item_id].sale_location_mode != "ALLOW_LIST",
                    )
                    else Decimal(0)
                ),
                minimum_remaining_days=items[native.item_id].minimum_remaining_days,
                opening_quantity=str(totals["opening"]),
                inward_quantity=str(totals["inward"]),
                outward_quantity=str(totals["outward"]),
                reserved=None,
                carrying_value=value,
                costing_method=pool.method,
                valuation_detail=detail,
                origins=residual,
                lot_id=native.lot_id,
                lot_code=lot.code if lot else None,
                manufacture_date=lot.manufactured_on if lot else None,
                expiry_date=lot.expires_on if lot else None,
                serials=sorted(serials[native.id]),
            )
            records.append(
                (
                    source_id(company, "POSITION", native.id),
                    {"payload": position.model_dump(mode="json")},
                )
            )
    coverage = Coverage(
        as_of=as_of,
        history_start=setup.books_begin_date,
        classification_date=as_of,
        timezone=setup.timezone,
        currency=setup.base_currency,
        policy_hash=policy_hash,
        complete_company=True,
        captured_at=utcnow(),
        item_count=len(items),
        location_count=len(locations),
        group_count=len(kinds["GROUP"]),
        position_count=len(positions),
        movement_count=len(handed_off),
        movements_complete=len(handed_off) == len(movements),
        valuation_complete=valuation_complete,
        reservations_complete=False,
        orders_complete=False,
        origins_complete=origins_complete,
        gl_complete=False,
    )
    records.append((coverage_id, {"payload": coverage.model_dump(mode="json")}))
    # Revalidating an unchanged owner state must not append a new reporting change
    # solely because wall-clock time advanced. Date, policy and every stock fact
    # still participate in this comparison.
    prior = {row.id: row.payload for row in previous if row.payload["kind"] != "MOVEMENT"}
    current = {identity: value["payload"] for identity, value in records}

    def comparable(value: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in value.items() if k != "captured_at"}

    if prior.keys() == current.keys() and all(
        comparable(prior[k]) == comparable(current[k]) for k in prior
    ):
        return
    desired = {identity for identity, _ in records}
    for row in previous:
        if row.payload["kind"] != "MOVEMENT" and row.id not in desired:
            if coverage_id not in {r.id for r in previous}:
                raise ConflictError("unrecognized external stock master source cannot be replaced")
            await db.delete(row)
    for first in range(0, len(records), 200):
        await publish(db, tenant=tenant, company=company, records=records[first : first + 200])


async def prepare(factory: Any, settings: Any, tenant: uuid.UUID, company: uuid.UUID) -> None:
    """Network acquisition precedes the Accounting transaction; lease spans commit."""
    from zoneinfo import ZoneInfo

    import httpx
    from billing_platform.db.types import utcnow
    from reporting_contract.catalog_stock import acquire, exchange
    from reporting_contract.enrollment import scope_allowed

    owner = settings.stock_report_catalog
    if owner is None:
        return
    if not await scope_allowed(owner, settings.report_enrollment_source, tenant, company):
        raise ConflictError("stock reporting scope is unavailable")
    async with factory() as db:
        setup = await db.scalar(select(FinancialSetup).where(FinancialSetup.company_id == company))
        if setup is None:
            raise ConflictError("initialize Accounting before preparing stock reports")
        as_of = utcnow().astimezone(ZoneInfo(setup.timezone)).date()
        if as_of < setup.books_begin_date:
            # Financial preparation may finish before books start; never invent stock zero.
            return
    identity = uuid.uuid4()
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        lease, masters = await acquire(
            client, owner, tenant=tenant, company=company, identity=identity, as_of=as_of
        )
        try:
            async with factory.begin() as db:
                if lease.expires_at <= utcnow() + dt.timedelta(seconds=10):
                    raise ConflictError("Catalog stock source lease is too old to publish")
                await publish_complete(
                    db,
                    tenant=tenant,
                    company=company,
                    as_of=as_of,
                    masters=masters,
                    policy_hash=lease.policy_hash,
                )
                if lease.expires_at <= utcnow():
                    raise ConflictError("Catalog stock source lease expired before publication")
        finally:
            await exchange(
                client,
                owner,
                "/internal/v1/stock-report-sources",
                {
                    "tenant_id": str(tenant),
                    "company_id": str(company),
                    "source_id": str(identity),
                    "as_of": as_of.isoformat(),
                    "offset": 0,
                    "release": True,
                },
            )
