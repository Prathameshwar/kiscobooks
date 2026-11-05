from __future__ import annotations

import secrets
import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.tenant_context import tenant_scope
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.listing import (
    FilterColumn,
    ListQuery,
    SortColumn,
    SortKind,
    apply_filters,
    apply_search,
    fetch_page,
    resolve_sort,
)
from billing_platform.pagination import CursorCodec
from tests.models import TenantThing


class Item(BaseModel):
    id: uuid.UUID
    name: str
    amount: Decimal | None


def _columns(nulls: str = "last") -> dict[str, SortColumn]:
    return {
        "id": SortColumn(TenantThing.id, "uuid"),
        "name": SortColumn(TenantThing.name, "text"),
        "amount": SortColumn(
            TenantThing.amount,
            "decimal",
            nullable=True,
            nulls="first" if nulls == "first" else "last",
        ),
    }


@pytest.mark.parametrize("nulls", ["first", "last"])
@pytest.mark.parametrize("order", ["amount,name", "-amount,name", "name,-amount", "-name,amount"])
async def test_mixed_order_ties_nulls_and_tenant_isolation(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    nulls: str,
    order: str,
) -> None:
    source = [("A", None), ("A", "1"), ("A", "1"), ("B", "1"), ("C", "2"), ("D", None)]
    for tenant in (tenant_a, tenant_b):
        for name, amount in source:
            session.add(
                TenantThing(
                    id=uuid7(),
                    tenant_id=tenant,
                    name=name,
                    amount=None if amount is None else Decimal(amount),
                )
            )
    await session.commit()
    columns = _columns(nulls)
    terms = resolve_sort(
        order,
        default="name",
        columns=columns,
        readable=frozenset(columns),
        supported=frozenset({tuple(order.split(","))}),
    )
    codec = CursorCodec(secrets.token_bytes(32), context="scoped-query")
    statement = select(TenantThing.id, TenantThing.name, TenantThing.amount)
    with tenant_scope(tenant_a):
        complete = await fetch_page(
            session,
            statement,
            query=ListQuery(limit=200),
            terms=terms,
            codec=codec,
            project=Item.model_validate,
        )
        found: list[Item] = []
        cursor = None
        while True:
            page = await fetch_page(
                session,
                statement,
                query=ListQuery(limit=2, cursor=cursor),
                terms=terms,
                codec=codec,
                project=Item.model_validate,
            )
            found.extend(page.items)
            if not page.page.has_more:
                assert page.page.next_cursor is None
                break
            cursor = page.page.next_cursor
    assert found == complete.items
    assert len(found) == len({item.id for item in found}) == 6
    if order.startswith("amount") or order.startswith("-amount"):
        amounts = [item.amount for item in found]
        assert (amounts[:2] if nulls == "first" else amounts[-2:]) == [None, None]


async def test_filters_search_escaping_and_lean_single_query(
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    with tenant_scope(tenant_a):
        for name in ("A%_real", "Axxreal", "Other"):
            session.add(TenantThing(id=uuid7(), tenant_id=tenant_a, name=name, amount=Decimal("1")))
        await session.commit()
        statement = select(TenantThing.id, TenantThing.name, TenantThing.amount)
        readable = frozenset(_columns())
        statement = apply_filters(
            statement,
            {"minimum": Decimal("1"), "names": ["A%_real", "Other"]},
            filters={
                "minimum": FilterColumn("amount", TenantThing.amount, "gte"),
                "names": FilterColumn("name", TenantThing.name, "in"),
            },
            readable=readable,
        )
        statement = apply_search(
            statement, " A%_ ", columns={"name": TenantThing.name}, readable=readable
        )
        terms = resolve_sort(
            None,
            default="name",
            columns=_columns(),
            readable=readable,
            supported=frozenset({("name",)}),
        )
        queries: list[str] = []

        def capture(
            conn: Any, cursor: Any, sql: str, params: Any, context: Any, many: bool
        ) -> None:
            queries.append(sql)

        event.listen(session.get_bind(), "before_cursor_execute", capture)
        try:
            page = await fetch_page(
                session,
                statement,
                query=ListQuery(),
                terms=terms,
                codec=CursorCodec(secrets.token_bytes(32), context="q"),
                project=Item.model_validate,
            )
        finally:
            event.remove(session.get_bind(), "before_cursor_execute", capture)
    assert [item.name for item in page.items] == ["A%_real"]
    assert len(queries) == 1
    assert "currency" not in queries[0] and "created_at" not in queries[0]


def test_denied_query_fields_and_invalid_combinations() -> None:
    columns = _columns()
    statement = select(TenantThing.id, TenantThing.name)
    with pytest.raises(PermissionDeniedError):
        resolve_sort(
            "amount",
            default="name",
            columns=columns,
            readable=frozenset({"id", "name"}),
            supported=frozenset({("amount",)}),
        )
    with pytest.raises(PermissionDeniedError):
        apply_search(statement, "AA", columns={"name": TenantThing.name}, readable=frozenset())
    with pytest.raises(PermissionDeniedError):
        apply_filters(
            statement,
            {"name": "secret"},
            filters={"name": FilterColumn("name", TenantThing.name)},
            readable=frozenset(),
        )
    for value in ("name,name", "name;drop", "unknown", "name,amount,id,name", "name,-amount"):
        with pytest.raises(ValidationFailedError):
            resolve_sort(
                value,
                default="name",
                columns=columns,
                readable=frozenset(columns),
                supported=frozenset({("name",)}),
            )
    values: dict[str, Any]
    for values in ({"bad": "x"}, {"name": []}, {"name": ["a"] * 101}):
        with pytest.raises(ValidationFailedError):
            apply_filters(
                statement,
                values,
                filters={"name": FilterColumn("name", TenantThing.name, "in")},
                readable=frozenset(columns),
            )
    for text in ("a", "a" * 201):
        with pytest.raises(ValidationFailedError):
            apply_search(
                statement, text, columns={"name": TenantThing.name}, readable=frozenset(columns)
            )
    assert ListQuery(q="   two   words ").q == "two words"
    for values in ({"limit": 201}, {"offset": 100}, {"q": "a" * 201}):
        with pytest.raises(ValidationError):
            ListQuery.model_validate(values)


async def test_bad_cursor_positions_and_full_entity_refused(
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    columns = _columns()
    terms = resolve_sort(
        None,
        default="name",
        columns=columns,
        readable=frozenset(columns),
        supported=frozenset({("name",)}),
    )
    codec = CursorCodec(secrets.token_bytes(32), context="q")
    with tenant_scope(tenant_a):
        for position in ({"id": "bad", "name": "A"}, {"wrong": "A"}, {"id": None, "name": "A"}):
            with pytest.raises(ValidationFailedError):
                await fetch_page(
                    session,
                    select(TenantThing.id, TenantThing.name),
                    query=ListQuery(cursor=codec.encode(position)),
                    terms=terms,
                    codec=codec,
                    project=Item.model_validate,
                )
        with pytest.raises(ValueError, match="explicit columns"):
            await fetch_page(
                session,
                select(TenantThing),
                query=ListQuery(),
                terms=terms,
                codec=codec,
                project=Item.model_validate,
            )


def test_cursor_scalar_encoding_preserves_exact_types() -> None:
    import datetime as dt

    from billing_platform.listing import _parse_value, _wire_value

    values: dict[SortKind, Any] = {
        "integer": 42,
        "boolean": True,
        "text": "00123",
        "uuid": uuid7(),
        "date": dt.date(2026, 9, 11),
        "datetime": dt.datetime(2026, 9, 11, tzinfo=dt.UTC),
        "decimal": Decimal("0.0001"),
    }
    for kind, value in values.items():
        spec = SortColumn(TenantThing.id, kind)
        assert _parse_value(_wire_value(value), spec) == value
    bad_values: list[tuple[SortKind, Any]] = [
        ("datetime", "2026-09-11"),
        ("decimal", "NaN"),
        ("integer", "1"),
        ("integer", True),
        ("text", 1.2),
    ]
    for kind, value in bad_values:
        with pytest.raises(ValueError):
            _parse_value(value, SortColumn(TenantThing.id, kind))
    assert _wire_value(None) is None
    with pytest.raises(ValueError):
        _wire_value(1.2)


def test_exact_search_range_filters_and_sort_contract_errors() -> None:
    columns = _columns()
    readable = frozenset(columns)
    statement = select(TenantThing.id, TenantThing.name, TenantThing.amount)
    assert apply_search(statement, None, columns={}, readable=readable) is statement
    exact = apply_search(
        statement,
        "A%",
        columns={"name": TenantThing.name},
        exact=frozenset({"name"}),
        readable=readable,
    )
    assert "LIKE" not in str(exact) and "A%" not in str(exact)
    with pytest.raises(ValueError):
        apply_search(
            statement,
            "AA",
            columns={"name": TenantThing.name},
            exact=frozenset({"unknown"}),
            readable=readable,
        )
    ranged = apply_filters(
        statement,
        {"name": "A", "maximum": Decimal("2")},
        filters={
            "name": FilterColumn("name", TenantThing.name),
            "maximum": FilterColumn("amount", TenantThing.amount, "lte"),
        },
        readable=readable,
    )
    assert "<=" in str(ranged)
    with pytest.raises(ValueError):
        apply_filters(
            statement,
            {"name": "A"},
            filters={"name": FilterColumn("name", TenantThing.name, cast(Any, "bad"))},
            readable=readable,
        )
    with pytest.raises(ValidationFailedError):
        resolve_sort(
            "id,name",
            default="name",
            columns=columns,
            readable=readable,
            supported=frozenset({("id", "name")}),
        )
    with pytest.raises(ValueError):
        resolve_sort(
            "name",
            default="name",
            columns=columns,
            readable=frozenset({"name"}),
            supported=frozenset({("name",)}),
        )
    assert (
        resolve_sort(
            "id", default="name", columns=columns, readable=readable, supported=frozenset({("id",)})
        )[0].key
        == "id"
    )
    assert ListQuery(q=None).q is None and ListQuery(q="   ").q is None


async def test_empty_and_invalid_page_projections(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    columns = _columns()
    terms = resolve_sort(
        "name",
        default="name",
        columns=columns,
        readable=frozenset(columns),
        supported=frozenset({("name",)}),
    )
    codec = CursorCodec(secrets.token_bytes(32), context="q")
    with tenant_scope(tenant_a):
        page = await fetch_page(
            session,
            select(TenantThing.id, TenantThing.name, TenantThing.amount),
            query=ListQuery(),
            terms=terms,
            codec=codec,
            project=Item.model_validate,
        )
        assert page.items == [] and not page.page.has_more and page.page.next_cursor is None
        with pytest.raises(ValueError):
            await fetch_page(
                session,
                select(TenantThing.id),
                query=ListQuery(),
                terms=terms,
                codec=codec,
                project=Item.model_validate,
            )
        with pytest.raises(ValueError):
            await fetch_page(
                session,
                select(TenantThing.id),
                query=ListQuery(),
                terms=(),
                codec=codec,
                project=Item.model_validate,
            )

@pytest.mark.parametrize("values", [[], ["a", "b"]])
def test_seek_rejects_incomplete_or_extra_cursor_values(values):
    from billing_platform.listing import SortTerm, seek_after

    with pytest.raises(ValueError, match="ordering"):
        seek_after([SortTerm("name", False, SortColumn(TenantThing.name, "text"))], values)
    with pytest.raises(ValueError, match="ordering"):
        seek_after([], [])
