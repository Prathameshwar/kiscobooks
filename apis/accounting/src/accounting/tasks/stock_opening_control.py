"""Reviewed cutover, immutable cohort claims and one native trading fence."""

import hashlib
import uuid
from decimal import Decimal
from typing import Any, Literal, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError
from billing_platform.field_policy import denied_fields
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    canonical_json,
    execute_idempotent,
)
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased
from voucher_execution.stock import StockInput, StockLine

from accounting.api.auth import Access
from accounting.domain.opening_errors import OpeningConflictError as ConflictError
from accounting.models.ledger import Journal
from accounting.models.stock import StockCostPool, StockMovement, StockPosition, StockPosting
from accounting.models.stock_opening import (
    StockOpeningClaim,
    StockOpeningControl,
    StockOpeningRevision,
)
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.schemas.stock_opening import (
    OpeningControlDetail,
    OpeningFinalize,
    OpeningManifest,
    OpeningReplace,
    OpeningZeroConfirm,
)
from accounting.stock_resources import STOCK_MOVEMENT, STOCK_POSITION, STOCK_POSTING
from accounting.tasks.access import authorize, readable, rules, writable
from accounting.tasks.commands import setup_lock
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.openings import require_opening_revision_window
from accounting.tasks.stock_reads import view
from accounting.tasks.stock_reconciliation import assert_physical, assert_value_control
from accounting.tasks.voucher_money_effects import audit, values


def require_access(current: Access, *, manage: bool = False) -> None:
    financial_context(current)
    authorize(current, STOCK_POSITION, "read")
    if not {"item_id", "warehouse_id", "bin_id", "lot_id", "quantity"} <= readable(
        current, STOCK_POSITION
    ):
        raise PermissionDeniedError("opening physical dimensions and quantity must be readable")
    if (
        not {
            "item_id",
            "warehouse_id",
            "bin_id",
            "lot_id",
            "quantity",
            "value",
            "currency",
        }
        <= view(current, STOCK_MOVEMENT)[2]
    ):
        raise PermissionDeniedError("opening quantities, dimensions and value must be readable")
    if manage:
        for key in ("accounting.finance.manage", "accounting.stock.configure"):
            current.actor.require_scope(
                key, target=ScopePath(company_id=current.context.company_id)
            )


async def control(db: AsyncSession, company: uuid.UUID) -> StockOpeningControl | None:
    return cast(
        StockOpeningControl | None,
        await db.scalar(
            select(StockOpeningControl)
            .where(StockOpeningControl.company_id == company, StockOpeningControl.item_id.is_(None))
            .with_for_update()
        ),
    )


def require_capture_read(current: Access) -> None:
    require_access(current)
    blocked = denied_fields(
        frozenset(StockLine.model_fields),
        rules=rules(current, STOCK_MOVEMENT, None),
        access="read",
        target=ScopePath(company_id=current.context.company_id),
    )
    if blocked:
        raise PermissionDeniedError("opening capture evidence is not readable")


async def active_claims(db: AsyncSession, row: StockOpeningControl) -> list[StockOpeningClaim]:
    reversed_posting = aliased(StockPosting)
    result = list(
        await db.scalars(
            select(StockOpeningClaim)
            .join(StockPosting, StockPosting.id == StockOpeningClaim.posting_id)
            .outerjoin(
                reversed_posting,
                (reversed_posting.company_id == row.company_id)
                & (reversed_posting.reverses_id == StockPosting.id),
            )
            .where(
                StockOpeningClaim.company_id == row.company_id,
                StockOpeningClaim.control_id == row.id,
                reversed_posting.id.is_(None),
            )
            .order_by(StockOpeningClaim.source_key)
            .limit(1001)
        )
    )
    if len(result) > 1000 or len({claim.source_key for claim in result}) != len(result):
        raise ConflictError("opening cohort claims require reconciliation")
    return result


async def pending(db: AsyncSession, company: uuid.UUID) -> bool:
    prepared = (
        await db.scalar(
            select(VoucherMoneyIntent.id)
            .where(
                VoucherMoneyIntent.company_id == company, VoucherMoneyIntent.status == "PREPARED"
            )
            .limit(1)
        )
        is not None
    )
    if prepared:
        return True
    stock_intents = select(VoucherMoneyIntent.id).where(VoucherMoneyIntent.company_id == company)
    journals = select(Journal.id).where(Journal.company_id == company)
    return (
        await db.scalar(
            select(Outbox.id)
            .where(
                or_(Outbox.aggregate_id.in_(stock_intents), Outbox.aggregate_id.in_(journals)),
                Outbox.event_type.in_(
                    (
                        "accounting.stock_posting.confirm",
                        "accounting.stock_posting.abort",
                        "accounting.company_posting.confirm",
                        "accounting.company_posting.abort",
                    )
                ),
                Outbox.published_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


async def require_no_trading(db: AsyncSession, company: uuid.UUID) -> None:
    cancelled = aliased(StockPosting)
    trading = await db.scalar(
        select(StockPosting.id)
        .outerjoin(
            cancelled,
            (cancelled.company_id == company) & (cancelled.reverses_id == StockPosting.id),
        )
        .where(
            StockPosting.company_id == company,
            StockPosting.action.not_in(("OPENING", "REVERSAL")),
            cancelled.id.is_(None),
        )
        .limit(1)
    )
    if trading:
        raise ConflictError("CORRECTION_HAS_DEPENDENCIES: reverse dependent trading first")
    if await pending(db, company):
        raise ConflictError("EXECUTION_UNCONFIRMED: reconcile pending execution first")


async def detail(
    db: AsyncSession, current: Access, row: StockOpeningControl
) -> OpeningControlDetail:
    require_capture_read(current)
    manifest = OpeningManifest.model_validate(row.manifest)
    applied = {claim.source_key for claim in await active_claims(db, row)}
    expected = {line.opening.source_key: line for line in manifest.lines if line.opening}
    if applied - set(expected):
        raise ConflictError("opening claims differ from the immutable manifest")
    missing = sorted(set(expected) - applied)
    blockers = ["OPENING_COHORTS_MISSING"] if missing else []
    if await pending(db, row.company_id):
        blockers.append("EXECUTION_UNCONFIRMED")
    return OpeningControlDetail(
        id=row.id,
        company_id=row.company_id,
        item_id=row.item_id,
        expected_version=row.row_version,
        status=row.status,
        books_begin_date=row.books_begin_date,
        currency=row.currency,
        manifest_hash=row.manifest_hash,
        expected_cohorts=len(expected),
        applied_cohorts=len(applied),
        expected_value=sum(
            (line.received_value or Decimal(0) for line in expected.values()), start=Decimal(0)
        ),
        applied_value=sum(
            (expected[key].received_value or Decimal(0) for key in applied), start=Decimal(0)
        ),
        missing_source_keys=missing,
        blockers=blockers,
        legacy_adopted=manifest.adopt_existing,
    )


async def register(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    body: OpeningManifest,
    key: str,
    *,
    item_id: uuid.UUID | None = None,
) -> Any:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        require_access(current, manage=True)
        writable(current, STOCK_POSTING, {}, {"reason": body.reason})
        for line in body.lines:
            writable(current, STOCK_MOVEMENT, {}, line.model_dump(exclude_none=True))

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, current)
        finance = financial_context(current)
        if body.adopt_existing:
            raise ConflictError("use the reviewed legacy adoption action for existing history")
        if (
            body.stock_date != finance.books_begin_date
            or body.currency != current.context.base_currency
        ):
            raise ConflictError("OPENING_DATE_MISMATCH: use company books begin and base currency")
        await require_opening_revision_window(db, current, body.stock_date)
        baseline = await control(db, current.context.company_id)
        if item_id is not None:
            if baseline is None or baseline.status != "FINALIZED":
                raise ConflictError("finish the company opening setup before adding product stock")
            if (
                body.opening_mode != "COMBINED"
                or not body.lines
                or any(line.item_id != item_id for line in body.lines)
                or len({line.lot_id for line in body.lines}) != len(body.lines)
                or (len(body.lines) > 1 and any(line.lot_id is None for line in body.lines))
            ):
                raise ConflictError(
                    "product opening requires distinct batches or one untracked row"
                )
            if await db.scalar(
                select(StockOpeningControl.id).where(
                    StockOpeningControl.company_id == current.context.company_id,
                    StockOpeningControl.item_id == item_id,
                )
            ):
                raise ConflictError("OPENING_ALREADY_RECORDED: resume this product opening")
            if await db.scalar(
                select(StockMovement.id)
                .join(
                    StockPosition,
                    StockPosition.id == StockMovement.position_id,
                )
                .where(
                    StockMovement.company_id == current.context.company_id,
                    StockPosition.company_id == current.context.company_id,
                    StockPosition.item_id == item_id,
                )
                .limit(1)
            ):
                raise ConflictError("a product with stock history cannot receive a first opening")
        elif baseline is not None:
            raise ConflictError("OPENING_ALREADY_RECORDED: resume the existing cutover")
        if item_id is None and await db.scalar(
            select(StockPosting.id)
            .where(StockPosting.company_id == current.context.company_id)
            .limit(1)
        ):
            raise ConflictError("existing stock history requires reviewed legacy adoption")
        if await pending(db, current.context.company_id):
            raise ConflictError("EXECUTION_UNCONFIRMED: reconcile pending execution first")
        payload = body.model_dump(mode="json")
        digest = hashlib.sha256(canonical_json(payload, maximum_bytes=2_097_152)).hexdigest()
        row = StockOpeningControl(
            **values(current),
            currency=body.currency,
            books_begin_date=body.stock_date,
            status="OPEN",
            manifest=payload,
            manifest_hash=digest,
            **({"item_id": item_id, "company_slot": None} if item_id else {}),
        )
        db.add(row)
        await db.flush()
        db.add(
            StockOpeningRevision(
                **values(current),
                currency=row.currency,
                control_id=row.id,
                revision=row.row_version,
                manifest=payload,
                manifest_hash=digest,
            )
        )
        audit(db, current, row.id, "stock_opening_control", "create", reason=body.reason)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, StockOpeningControl, uuid.UUID(receipt["id"]), company_id=current.context.company_id
        )
        return await detail(db, current, row)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.stock_opening_control.create" + (".product" if item_id else ""),
            key,
            {**body.model_dump(mode="json"), **({"item_id": str(item_id)} if item_id else {})},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )


async def finalize(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    identity: uuid.UUID,
    body: OpeningFinalize,
    key: str,
) -> Any:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        require_access(current, manage=True)
        writable(current, STOCK_POSTING, {}, {"reason": body.reason})

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, current)
        row = await company_object(
            db, StockOpeningControl, identity, company_id=current.context.company_id, lock=True
        )
        if row.row_version != body.expected_version or row.manifest_hash != body.manifest_hash:
            raise ConflictError("REVIEW_STALE: review current opening reconciliation")
        if row.status != "OPEN":
            raise ConflictError("OPENING_FINALIZED: cutover is already finalized")
        await require_opening_revision_window(db, current, row.books_begin_date)
        review = await detail(db, current, row)
        if review.blockers:
            raise ConflictError("opening finalization blocked: " + ", ".join(review.blockers))
        await assert_physical(db, row.company_id)
        await assert_value_control(db, row.company_id)
        row.status = "FINALIZED"
        row.finalized_at = utcnow()
        row.row_version += 1
        row.updated_by = current.actor.user_id
        audit(db, current, row.id, "stock_opening_control", "finalize", reason=body.reason)
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, StockOpeningControl, identity, company_id=current.context.company_id
        )
        return await detail(db, current, row)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.stock_opening_control.finalize",
            key,
            {"id": str(identity), **body.model_dump(mode="json")},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )


async def confirm_zero(
    factory: async_sessionmaker[AsyncSession], current: Access, body: OpeningZeroConfirm, key: str
) -> Any:
    def require_zero() -> None:
        require_access(current)
        target = ScopePath(company_id=current.context.company_id)
        if not any(
            current.actor.allows_scope(permission, target=target)
            for permission in ("opening_balance.initialize_zero", "accounting.finance.manage")
        ):
            current.actor.require_scope("opening_balance.initialize_zero", target=target)
        writable(current, STOCK_POSTING, {}, {"reason": body.reason})

    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        require_zero()

    async def mutate(db: AsyncSession) -> CommandReceipt:
        setup = await setup_lock(db, current)
        if setup.generation != body.expected_generation + 1:
            raise ConflictError("REVIEW_STALE: review the latest stock opening readiness")
        company = current.context.company_id
        if await control(db, company) is not None or await pending(db, company):
            raise ConflictError(
                "existing cutover or pending execution requires a financial controller"
            )
        for model in (StockPosting, StockPosition, StockCostPool):
            if await db.scalar(select(model.id).where(model.company_id == company).limit(1)):
                raise ConflictError("existing stock history requires reviewed reconciliation")
        finance = financial_context(current)
        # This is an explicit zero declaration, not permission to post balances.
        # Inspect period state without requiring/granting period.post.
        from accounting.models.fiscal import FiscalPeriod

        periods = list(
            await db.scalars(
                select(FiscalPeriod)
                .where(
                    FiscalPeriod.company_id == company,
                    FiscalPeriod.start_date <= finance.books_begin_date,
                    FiscalPeriod.end_date >= finance.books_begin_date,
                )
                .limit(2)
            )
        )
        closed = await db.scalar(
            select(FiscalPeriod.id)
            .where(
                FiscalPeriod.company_id == company,
                FiscalPeriod.end_date >= finance.books_begin_date,
                FiscalPeriod.status.in_(("CLOSED", "LOCKED")),
            )
            .limit(1)
        )
        if len(periods) != 1 or periods[0].status != "OPEN" or closed:
            raise ConflictError("opening period must be open without later closed or locked books")
        await assert_physical(db, company)
        await assert_value_control(db, company)
        manifest = OpeningManifest(
            stock_date=finance.books_begin_date,
            currency=current.context.base_currency,
            opening_mode="COMBINED",
            reason=body.reason,
        )
        payload = manifest.model_dump(mode="json")
        digest = hashlib.sha256(canonical_json(payload)).hexdigest()
        row = StockOpeningControl(
            **values(current),
            currency=manifest.currency,
            books_begin_date=manifest.stock_date,
            status="FINALIZED",
            finalized_at=utcnow(),
            manifest=payload,
            manifest_hash=digest,
        )
        db.add(row)
        await db.flush()
        db.add(
            StockOpeningRevision(
                **values(current),
                currency=row.currency,
                control_id=row.id,
                revision=row.row_version,
                manifest=payload,
                manifest_hash=digest,
            )
        )
        audit(db, current, row.id, "stock_opening_control", "confirm_zero", reason=body.reason)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, StockOpeningControl, uuid.UUID(receipt["id"]), company_id=current.context.company_id
        )
        return await detail(db, current, row)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.stock_opening_control.confirm_zero",
            key,
            body.model_dump(mode="json"),
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )


async def require_posting(
    db: AsyncSession, company: uuid.UUID, body: StockInput
) -> StockOpeningControl | None:
    row = await control(db, company)
    if body.action != "OPENING":
        if row is None or row.status != "FINALIZED":
            raise ConflictError(
                "OPENING_NOT_FINALIZED: confirm zero stock or complete the opening cutover"
            )
        if await db.scalar(
            select(StockOpeningControl.id)
            .where(
                StockOpeningControl.company_id == company,
                StockOpeningControl.item_id.in_({line.item_id for line in body.lines}),
                StockOpeningControl.status != "FINALIZED",
            )
            .limit(1)
        ):
            raise ConflictError("PRODUCT_OPENING_PENDING: finish this product's opening first")
        return row
    selected = await db.scalar(
        select(StockOpeningControl)
        .where(
            StockOpeningControl.company_id == company,
            StockOpeningControl.id == body.opening_control_id,
        )
        .with_for_update()
    )
    if selected is not None and selected.item_id is not None:
        if row is None or row.status != "FINALIZED":
            raise ConflictError("company opening setup is not complete")
        if any(line.item_id != selected.item_id for line in body.lines):
            raise ConflictError("opening belongs to another product")
        if await db.scalar(
            select(StockMovement.id)
            .join(
                StockPosition,
                StockPosition.id == StockMovement.position_id,
            )
            .where(
                StockMovement.company_id == company,
                StockPosition.company_id == company,
                StockPosition.item_id == selected.item_id,
            )
            .limit(1)
        ):
            raise ConflictError("this product already has stock history")
    row = selected
    if row is None or row.status != "OPEN":
        raise ConflictError("OPENING_FINALIZED: select an open reviewed cutover manifest")
    expected = OpeningManifest.model_validate(row.manifest)
    if (body.currency, body.stock_date, body.opening_mode) != (
        expected.currency,
        expected.stock_date,
        expected.opening_mode,
    ):
        raise ConflictError("stock opening differs from its cutover manifest")
    claimed = {claim.source_key for claim in await active_claims(db, row)}
    lines = {line.opening.source_key: line for line in expected.lines if line.opening}
    current_keys = {line.opening.source_key for line in body.lines if line.opening}
    # Native FIFO uses committed owner order to break equal-date ties. Keep
    # separate chunks in their reviewed cohort order within each warehouse pool.
    remaining: dict[tuple[uuid.UUID, uuid.UUID], list[StockLine]] = {}
    for candidate in sorted(
        expected.lines,
        key=lambda line: (
            line.opening.received_on or expected.stock_date,
            line.opening.cohort_order,
            line.opening.source_key,
        )
        if line.opening
        else (expected.stock_date, 1, str(line.line_id)),
    ):
        if candidate.opening and candidate.opening.source_key not in claimed:
            remaining.setdefault((candidate.item_id, candidate.warehouse_id), []).append(candidate)
    for candidates in remaining.values():
        selected_lines = [
            candidate
            for candidate in candidates
            if candidate.opening and candidate.opening.source_key in current_keys
        ]
        if selected_lines != candidates[: len(selected_lines)]:
            raise ConflictError(
                "OPENING_COHORT_ORDER: post earlier reviewed warehouse cohorts first"
            )
    for line in body.lines:
        if not line.opening or line.opening.source_key in claimed:
            raise ConflictError(
                "OPENING_ALREADY_RECORDED: opening cohort is absent or already posted"
            )
        original = lines.get(line.opening.source_key)
        if original is None or original.model_dump(mode="json") != line.model_dump(mode="json"):
            raise ConflictError("REVIEW_STALE: stock cohort differs from the reviewed manifest")
    return row


async def revise_control(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    identity: uuid.UUID | None,
    action: Literal["reopen", "replace", "adopt"],
    body: OpeningFinalize | OpeningReplace | OpeningManifest,
    key: str,
) -> Any:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        require_access(current, manage=True)
        writable(current, STOCK_POSTING, {}, {"reason": body.reason})
        if isinstance(body, OpeningReplace):
            for line in body.manifest.lines:
                writable(current, STOCK_MOVEMENT, {}, line.model_dump(exclude_none=True))

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, current)
        finance = financial_context(current)
        if action == "adopt":
            assert isinstance(body, OpeningManifest)
            if (
                not body.adopt_existing
                or body.lines
                or body.stock_date != finance.books_begin_date
                or body.currency != current.context.base_currency
            ):
                raise ConflictError("adoption acknowledges existing history without new quantities")
            await require_opening_revision_window(db, current, body.stock_date)
            if await control(db, current.context.company_id) is not None:
                raise ConflictError("an opening control already exists")
            if not await db.scalar(
                select(StockPosting.id)
                .where(StockPosting.company_id == current.context.company_id)
                .limit(1)
            ):
                raise ConflictError("no legacy stock exists; declare an opening or zero stock")
            if await pending(db, current.context.company_id):
                raise ConflictError("reconcile pending execution before adopting existing stock")
            await assert_physical(db, current.context.company_id)
            await assert_value_control(db, current.context.company_id)
            payload = body.model_dump(mode="json")
            digest = hashlib.sha256(canonical_json(payload)).hexdigest()
            row = StockOpeningControl(
                **values(current),
                currency=body.currency,
                books_begin_date=body.stock_date,
                status="FINALIZED",
                finalized_at=utcnow(),
                manifest=payload,
                manifest_hash=digest,
            )
            db.add(row)
            await db.flush()
            db.add(
                StockOpeningRevision(
                    **values(current),
                    currency=row.currency,
                    control_id=row.id,
                    revision=row.row_version,
                    manifest=payload,
                    manifest_hash=digest,
                )
            )
        else:
            assert identity is not None and isinstance(body, OpeningFinalize)
            row = await company_object(
                db, StockOpeningControl, identity, company_id=current.context.company_id, lock=True
            )
            if row.row_version != body.expected_version or row.manifest_hash != body.manifest_hash:
                raise ConflictError("REVIEW_STALE: review the latest cutover before correction")
            if row.item_id is not None:
                raise ConflictError(
                    "product openings retain their first-entry evidence; use native reversal"
                )
            await require_opening_revision_window(db, current, row.books_begin_date)
            if action == "reopen" and OpeningManifest.model_validate(row.manifest).adopt_existing:
                raise ConflictError(
                    "legacy adoption cannot become a new opening; use native source corrections"
                )
            await require_no_trading(db, row.company_id)
            if action == "reopen":
                if row.status != "FINALIZED":
                    raise ConflictError("only a finalized cutover can be reopened")
                row.status = "OPEN"
                row.finalized_at = None
                row.row_version += 1
            else:
                assert isinstance(body, OpeningReplace)
                if row.status != "OPEN" or await active_claims(db, row):
                    raise ConflictError(
                        "reverse every applied opening cohort before replacing its manifest"
                    )
                if (
                    body.manifest.stock_date != row.books_begin_date
                    or body.manifest.currency != row.currency
                    or body.manifest.adopt_existing
                ):
                    raise ConflictError("replacement cannot change the cutover date or currency")
                row.row_version += 1
                row.manifest = body.manifest.model_dump(mode="json")
                row.manifest_hash = hashlib.sha256(
                    canonical_json(row.manifest, maximum_bytes=2_097_152)
                ).hexdigest()
                db.add(
                    StockOpeningRevision(
                        **values(current),
                        currency=row.currency,
                        control_id=row.id,
                        revision=row.row_version,
                        manifest=row.manifest,
                        manifest_hash=row.manifest_hash,
                    )
                )
            row.updated_by = current.actor.user_id
        audit(db, current, row.id, "stock_opening_control", action, reason=body.reason)
        return CommandReceipt(201 if action == "adopt" else 200, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, StockOpeningControl, uuid.UUID(receipt["id"]), company_id=current.context.company_id
        )
        return await detail(db, current, row)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.stock_opening_control." + action,
            key,
            {"id": str(identity) if identity else None, **body.model_dump(mode="json")},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )


async def claim(
    db: AsyncSession,
    current: Access,
    row: StockOpeningControl,
    posting: StockPosting,
    line: StockLine,
    movement_id: uuid.UUID,
) -> None:
    assert line.opening is not None
    db.add(
        StockOpeningClaim(
            **values(current),
            currency=posting.currency,
            control_id=row.id,
            source_key=line.opening.source_key,
            posting_id=posting.id,
            movement_id=movement_id,
        )
    )
    row.row_version += 1
    row.updated_by = current.actor.user_id
