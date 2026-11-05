"""Typed, bounded list mechanics over service-owned columns and access plans.

Callers supply a tenant/company-scoped explicit-column SELECT, current readable
fields and a cursor bound to the normalized query and current authority. This
module never selects an ORM entity, counts rows or invents a domain filter.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Select, and_, false, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.pagination import CursorCodec


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)
    q: str | None = Field(default=None, max_length=200)
    sort: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class PageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int
    has_more: bool
    next_cursor: str | None


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    page: PageMeta


type SortKind = Literal["text", "integer", "decimal", "date", "datetime", "uuid", "boolean"]


@dataclass(frozen=True, slots=True)
class SortColumn:
    column: ColumnElement[Any] | InstrumentedAttribute[Any]
    kind: SortKind
    nullable: bool = False
    nulls: Literal["first", "last"] = "last"


@dataclass(frozen=True, slots=True)
class SortTerm:
    key: str
    descending: bool
    definition: SortColumn


def resolve_sort(
    value: str | None,
    *,
    default: str,
    columns: Mapping[str, SortColumn],
    readable: frozenset[str],
    supported: frozenset[tuple[str, ...]],
) -> tuple[SortTerm, ...]:
    names = (value or default).split(",")
    if not 1 <= len(names) <= 3 or any(
        not re.fullmatch(r"-?[a-z][a-z0-9_]*", name) for name in names
    ):
        raise ValidationFailedError("sort requires one to three registered fields")
    keys = [name.removeprefix("-") for name in names]
    if len(set(keys)) != len(keys) or any(key not in columns for key in keys):
        raise ValidationFailedError("unknown or repeated sort field")
    if not set(keys) <= readable:
        raise PermissionDeniedError("a requested sort field is not readable")
    # Supported combinations correspond to reviewed service access indexes.
    if tuple(names) not in supported:
        raise ValidationFailedError("unsupported sort combination")
    if "id" in keys and keys[-1] != "id":
        raise ValidationFailedError("id must be the final sort field")
    if "id" not in keys:
        names.append("-id" if names[-1].startswith("-") else "id")
    if "id" not in readable or "id" not in columns or columns["id"].nullable:
        raise ValueError("a list requires a readable non-null unique id tie-breaker")
    return tuple(
        SortTerm(name.removeprefix("-"), name.startswith("-"), columns[name.removeprefix("-")])
        for name in names
    )


@dataclass(frozen=True, slots=True)
class FilterColumn:
    field_key: str
    column: ColumnElement[Any] | InstrumentedAttribute[Any]
    operator: Literal["eq", "in", "gte", "lte"] = "eq"


def apply_filters(
    statement: Select[Any],
    values: Mapping[str, Any],
    *,
    filters: Mapping[str, FilterColumn],
    readable: frozenset[str],
) -> Select[Any]:
    """Values must come from the service's extra-forbid typed filter model."""
    if len(values) > 16 or set(values) - set(filters):
        raise ValidationFailedError("unknown or excessive filters")
    for name, value in values.items():
        spec = filters[name]
        if spec.field_key not in readable:
            raise PermissionDeniedError("a requested filter field is not readable")
        col = spec.column
        if spec.operator == "eq":
            condition = col == value
        elif spec.operator == "in":
            if not isinstance(value, list | tuple) or not 1 <= len(value) <= 100:
                raise ValidationFailedError("in filters require one to one hundred values")
            condition = col.in_(value)
        elif spec.operator == "gte":
            condition = col >= value
        elif spec.operator == "lte":
            condition = col <= value
        else:
            raise ValueError("unsupported registered filter operator")
        statement = statement.where(condition)
    return statement


def apply_search(
    statement: Select[Any],
    query: str | None,
    *,
    columns: Mapping[str, ColumnElement[Any] | InstrumentedAttribute[Any]],
    readable: frozenset[str],
    exact: frozenset[str] = frozenset(),
    minimum_length: int = 2,
) -> Select[Any]:
    if query is None:
        return statement
    value = " ".join(query.split())
    if not minimum_length <= len(value) <= 200:
        raise ValidationFailedError("search text is outside the supported length")
    if not columns or not set(columns) <= readable:
        raise PermissionDeniedError("search requires access to its registered fields")
    if not exact <= set(columns):
        raise ValueError("exact search keys must be registered")
    escaped = value.replace("~", "~~").replace("%", "~%").replace("_", "~_")
    return statement.where(
        or_(
            *(
                col == value if key in exact else col.like(escaped + "%", escape="~")
                for key, col in columns.items()
            )
        )
    )


def _parse_value(value: Any, spec: SortColumn) -> Any:
    if value is None:
        if spec.nullable:
            return None
        raise ValueError("unexpected null cursor position")
    if spec.kind == "integer" and type(value) is int:
        return value
    if spec.kind == "boolean" and type(value) is bool:
        return value
    if not isinstance(value, str):
        raise ValueError("invalid cursor position type")
    if spec.kind == "text":
        return value
    if spec.kind == "uuid":
        return uuid.UUID(value)
    if spec.kind == "date":
        return dt.date.fromisoformat(value)
    if spec.kind == "datetime":
        moment = dt.datetime.fromisoformat(value)
        if moment.tzinfo is None:
            raise ValueError("cursor datetime requires timezone")
        return moment
    if spec.kind == "decimal":
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("cursor decimal must be finite")
        return number
    raise ValueError("invalid cursor position type")


def _wire_value(value: Any) -> Any:
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("unsupported cursor position type")


def _after(term: SortTerm, value: Any) -> ColumnElement[bool]:
    col, spec = term.definition.column, term.definition
    if value is None:
        return col.is_not(None) if spec.nulls == "first" else false()
    comparison = col < value if term.descending else col > value
    return or_(comparison, col.is_(None)) if spec.nullable and spec.nulls == "last" else comparison


def seek_after(terms: Sequence[SortTerm], values: Sequence[Any]) -> ColumnElement[bool]:
    """Seek using indexed scalar ranges, including mixed direction and explicit null order.

    MySQL may filter tuple comparisons after scanning the preceding index range.
    Callers must validate cursor values and choose an indexed deterministic order.
    """
    if not terms or len(terms) != len(values):
        raise ValueError("cursor values must match a nonempty ordering")
    branches = []
    prefix: list[ColumnElement[bool]] = []
    for term, value in zip(terms, values, strict=True):
        branches.append(and_(*prefix, _after(term, value)))
        prefix.append(term.definition.column == value)
    return or_(*branches)


async def fetch_page[T: BaseModel](
    db: AsyncSession,
    statement: Select[Any],
    *,
    query: ListQuery,
    terms: Sequence[SortTerm],
    codec: CursorCodec,
    project: Callable[[Mapping[str, Any]], T],
) -> Page[T]:
    """One SELECT of limit+1 rows with mixed-direction lexicographic seek.

    Null placement is explicit in both ORDER BY and seek. The caller's lean
    projection must contain each sort key; sensitive values must never be sorted.
    Pagination traverses live data, not a snapshot across independent requests.
    """
    if not terms or terms[-1].key != "id":
        raise ValueError("a page requires a unique final id sort")
    if any(term.key not in statement.selected_columns for term in terms):
        raise ValueError("sort keys must be present in the list projection")
    if any(isinstance(desc.get("expr"), type) for desc in statement.column_descriptions):
        raise ValueError("list SELECT must use explicit columns, not full ORM entities")
    if query.cursor:
        try:
            position = codec.decode(query.cursor)
            if set(position) != {term.key for term in terms}:
                raise ValueError("cursor keys differ from ordering")
            values = [_parse_value(position[term.key], term.definition) for term in terms]
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise ValidationFailedError("invalid cursor position") from exc
        statement = statement.where(seek_after(terms, values))
    ordering: list[ColumnElement[Any]] = []
    for term in terms:
        col, spec = term.definition.column, term.definition
        if spec.nullable:
            ordering.append(col.is_(None).asc() if spec.nulls == "last" else col.is_(None).desc())
        ordering.append(col.desc() if term.descending else col.asc())
    rows = (
        (await db.execute(statement.order_by(None).order_by(*ordering).limit(query.limit + 1)))
        .mappings()
        .all()
    )
    visible, has_more = rows[: query.limit], len(rows) > query.limit
    next_cursor = None
    if has_more:
        next_cursor = codec.encode({term.key: _wire_value(visible[-1][term.key]) for term in terms})
    return Page(
        items=[project(dict(row)) for row in visible],
        page=PageMeta(
            limit=query.limit,
            has_more=has_more,
            next_cursor=next_cursor,
        ),
    )
