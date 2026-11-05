"""Storage-scale stock totals suitable for exact SQL reconciliation predicates."""

from decimal import Decimal

from billing_platform.db.types import Money
from sqlalchemy import SQLColumnExpression, func, type_coerce
from sqlalchemy.sql import ColumnElement


def total(column: SQLColumnExpression[Decimal]) -> ColumnElement[Decimal]:
    # MySQL retains decimal arithmetic. SQLite NUMERIC can leave binary residue;
    # every contributing quantity/value column has exactly four stored decimals.
    return type_coerce(func.round(func.coalesce(func.sum(column), 0), 4), Money)
