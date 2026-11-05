"""Order independent stock writers by the serialized owner's commit generation.

UUID timestamps cluster storage; they cannot order commits across process clocks.
The common execution receipt owns the monotonic company generation. Low-level
ledger fixtures without an account policy predate that protocol and use UUIDs.
Public stock execution always retains both its policy and its owner receipt.
"""

import uuid

from billing_platform.errors import ConflictError
from pydantic import ValidationError
from sqlalchemy import SQLColumnExpression, case, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql.selectable import ScalarSelect
from voucher_execution import ExecutionResult

from accounting.models.stock import StockMovement, StockPosting
from accounting.models.voucher_execution import VoucherExecution


def generation(posting: type[StockPosting] | AliasedClass[StockPosting]) -> ScalarSelect[int]:
    return (
        select(VoucherExecution.result["committed_generation"].as_integer())
        .where(
            VoucherExecution.tenant_id == posting.tenant_id,
            VoucherExecution.company_id == posting.company_id,
            VoucherExecution.execution_id == posting.execution_id,
            VoucherExecution.operation_id == posting.operation_id,
            VoucherExecution.result["outcome"].as_string() == "COMMITTED",
        )
        .correlate(posting)
        .scalar_subquery()
    )


def movement_generation(
    company: uuid.UUID, movement: SQLColumnExpression[uuid.UUID]
) -> ScalarSelect[int]:
    """Receipt age ties use native commit order; only storage fixtures lack receipts."""
    ordinal = generation(StockPosting)
    return (
        select(
            case(
                (StockPosting.account_policy_id.is_(None), func.coalesce(ordinal, 0)),
                else_=ordinal,
            )
        )
        .select_from(StockMovement)
        .join(StockPosting, StockPosting.id == StockMovement.posting_id)
        .where(
            StockMovement.company_id == company,
            StockPosting.company_id == company,
            StockMovement.id == movement,
        )
        .correlate_except(StockMovement, StockPosting)
        .scalar_subquery()
    )


async def committed_generation(db: AsyncSession, posting: StockPosting) -> int | None:
    row = await db.scalar(
        select(VoucherExecution).where(
            VoucherExecution.company_id == posting.company_id,
            VoucherExecution.execution_id == posting.execution_id,
        )
    )
    if row is None and posting.account_policy_id is None:
        return None
    try:
        result = ExecutionResult.model_validate(row.result if row else None)
    except ValidationError as exc:
        raise ConflictError("stock committed owner receipt is unavailable") from exc
    effects = {(effect.effect_kind, effect.effect_id) for effect in result.effects}
    if (
        row is None
        or row.tenant_id != posting.tenant_id
        or result.tenant_id != posting.tenant_id
        or result.company_id != posting.company_id
        or result.execution_id != posting.execution_id
        or result.operation_id != posting.operation_id
        or result.content_hash != posting.content_hash
        or result.outcome != "COMMITTED"
        or ("STOCK", posting.id) not in effects
        or ("SOURCE_RECEIPT", row.id) not in effects
        or (posting.journal_id is not None and ("JOURNAL", posting.journal_id) not in effects)
    ):
        raise ConflictError("stock committed owner receipt does not bind its immutable effects")
    return result.committed_generation


async def assert_committed(
    db: AsyncSession, company: uuid.UUID, *, pending: uuid.UUID | None = None
) -> None:
    missing = await db.scalar(
        select(StockPosting.id)
        .where(
            StockPosting.company_id == company,
            StockPosting.account_policy_id.is_not(None),
            StockPosting.id != pending if pending else true(),
            generation(StockPosting).is_(None),
        )
        .limit(1)
    )
    if missing:
        raise ConflictError("stock committed owner generation is unavailable")
