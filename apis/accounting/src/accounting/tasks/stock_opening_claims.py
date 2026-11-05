"""One signed bridge-value expression for opening coverage, selection and claims."""

import uuid
from decimal import Decimal

from billing_platform.db.types import Money
from sqlalchemy import Select, SQLColumnExpression, case, func, select, type_coerce

from accounting.models.ledger import JournalLine
from accounting.models.stock import StockOpeningBridge, StockValueEntry


def claimed(
    company: uuid.UUID, line: uuid.UUID | SQLColumnExpression[uuid.UUID]
) -> Select[tuple[Decimal]]:
    return (
        select(
            type_coerce(
                func.coalesce(
                    func.sum(
                        case(
                            (StockValueEntry.amount >= 0, StockOpeningBridge.amount),
                            else_=-StockOpeningBridge.amount,
                        )
                    ),
                    0,
                ),
                Money,
            )
        )
        .select_from(StockOpeningBridge)
        .join(StockValueEntry, StockValueEntry.id == StockOpeningBridge.value_entry_id)
        .where(
            StockOpeningBridge.company_id == company,
            StockValueEntry.company_id == company,
            StockOpeningBridge.journal_line_id == line,
        )
        .correlate(JournalLine)
    )
