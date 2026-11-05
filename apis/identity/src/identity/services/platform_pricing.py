"""Catalog arithmetic and immutable version snapshots. Never executes a charge."""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models.platform_price import PlatformPrice, PlatformPriceRevision
from identity.schemas.platform_price import (
    PlatformPriceDetail,
    PlatformPriceInput,
    PriceCurrency,
    usd_amount,
)
from identity.services.audit import record


def detail(row: PlatformPrice) -> PlatformPriceDetail:
    body = PlatformPriceInput.model_validate(row)
    prices = []
    for currency in ("INR", "USD"):

        def amount(value: Decimal, quantum: str, currency: str = currency) -> Decimal:
            return (
                value.quantize(Decimal(quantum), rounding=ROUND_CEILING)
                if currency == "INR"
                else usd_amount(value, row.fx_inr_per_usd, quantum)
            )

        monthly = amount(row.monthly_fee, "0.01")
        net = monthly * row.term_months
        tax = (net * row.tax_percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        prices.append(
            PriceCurrency(
                currency=currency,
                monthly_fee=monthly,
                unit_price=amount(row.unit_price, "0.0001"),
                output_unit_price=amount(row.output_unit_price, "0.0001"),
                term_net=net,
                term_tax=tax,
                term_total=net + tax,
            )
        )
    return PlatformPriceDetail(
        **body.model_dump(),
        id=row.id,
        version=row.version,
        deleted_at=row.deleted_at,
        prices=prices,
    )


def snapshot(db: AsyncSession, row: PlatformPrice, current: Actor | None = None) -> None:
    db.add(
        PlatformPriceRevision(
            price_id=row.id,
            version=row.version,
            snapshot=detail(row).model_dump(mode="json"),
            created_at=utcnow(),
            created_by=current.user_id if current else None,
        )
    )


async def apply(
    db: AsyncSession, row: PlatformPrice, body: PlatformPriceInput, current: Actor
) -> PlatformPriceDetail:
    if row.code != body.code:
        raise ConflictError("pricing codes cannot be renamed; create a new offering instead")
    if row.deleted_at is not None:
        raise ConflictError("restore this deleted offering before editing")
    before = PlatformPriceInput.model_validate(row)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.version += 1
    row.updated_by = current.user_id
    if before.is_active != body.is_active:
        row.deactivated_at = None if body.is_active else utcnow()
        row.deactivated_by = None if body.is_active else current.user_id
    snapshot(db, row, current)
    record(
        db,
        current,
        action="platform.price_updated",
        entity="platform_price",
        entity_id=row.id,
        changes={
            "version": {"from": row.version - 1, "to": row.version},
            **{
                key: {"changed": True}
                for key in PlatformPriceInput.model_fields
                if getattr(before, key) != getattr(body, key)
            },
        },
    )
    await db.flush()
    return detail(row)


async def unique_code(db: AsyncSession, code: str) -> None:
    if await db.scalar(select(PlatformPrice.id).where(PlatformPrice.code == code)) is not None:
        raise ConflictError(
            "this pricing code already exists, including inactive or deleted offerings"
        )


def check_version(row: PlatformPrice | None, version: int) -> PlatformPrice:
    if row is None:
        raise NotFoundError("pricing offering not found")
    if row.version != version:
        raise ConflictError("this offering changed; reload it before saving")
    return row
