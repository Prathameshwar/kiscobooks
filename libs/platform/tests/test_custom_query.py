import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Boolean, Date, Numeric, String, select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.custom_fields import Choice, CustomDefinition, ValidationRules
from billing_platform.custom_query import (
    CustomPredicate,
    ReadyIndex,
    custom_predicate,
    definition_digest,
)
from billing_platform.db import create_session_factory, tenant_scope, unfiltered
from billing_platform.db.base import Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.ids import uuid7
from tests.models import CompanyThing


class ScalarFixture(IdMixin, TenantMixin, Base):
    __tablename__ = "custom_query_scalar_fixture"
    company_id: Mapped[Any] = mapped_column(Uuid7)
    entity_id: Mapped[Any] = mapped_column(Uuid7)
    entity_type: Mapped[str] = mapped_column(String(80))
    field_key: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int]
    value_text: Mapped[str | None] = mapped_column(String(512))
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    value_bool: Mapped[bool | None] = mapped_column(Boolean)
    value_date: Mapped[dt.date | None] = mapped_column(Date)
    value_datetime: Mapped[dt.datetime | None] = mapped_column("value_datetime_at", UtcDateTime)
    currency: Mapped[str | None] = mapped_column(String(3))


class MemberFixture(IdMixin, TenantMixin, Base):
    __tablename__ = "custom_query_member_fixture"
    company_id: Mapped[Any] = mapped_column(Uuid7)
    entity_id: Mapped[Any] = mapped_column(Uuid7)
    entity_type: Mapped[str] = mapped_column(String(80))
    field_key: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int]
    member_value: Mapped[str] = mapped_column(String(200))


def field(kind: str = "text", **changes: Any) -> CustomDefinition:
    args: dict[str, Any] = {"key": "cf_value", "data_type": kind, "is_searchable": True}
    if kind == "multi_select":
        args["choices"] = (Choice(value="a", label="A"), Choice(value="b", label="B"))
    return CustomDefinition(**{**args, **changes})


def build(definition: CustomDefinition, company: Any, op: str, value: Any, **changes: Any) -> Any:
    args = {
        "binding": ReadyIndex(definition, 1, definition_digest(definition)),
        "scalar_model": ScalarFixture,
        "member_model": MemberFixture,
        "owner_id": CompanyThing.id,
        "company_id": company,
        "entity_type": "test.company",
        "readable": frozenset({"custom_field:cf_value"}),
        "currencies": frozenset({"USD", "EUR"}),
    }
    return custom_predicate(
        CustomPredicate.model_validate({"key": "cf_value", "operator": op, "value": value}),
        **{**args, **changes},
    )


@pytest.mark.parametrize(
    "kind,stored,queries",
    [
        ("text", {"value_text": "hello"}, [("eq", " HELLO "), ("in", ["missing", "hello"])]),
        ("text", {"value_text": "HELLO"}, [("eq", "HELLO")]),
        ("integer", {"value_number": Decimal("2")}, [("eq", 2), ("gte", 1), ("lte", 3)]),
        ("decimal", {"value_number": Decimal("0.0001")}, [("eq", "0.0001")]),
        ("boolean", {"value_bool": False}, [("eq", False)]),
        ("date", {"value_date": dt.date(2026, 9, 1)}, [("eq", "2026-09-01")]),
        (
            "datetime",
            {"value_datetime": dt.datetime(2026, 9, 1, tzinfo=dt.UTC)},
            [("eq", "2026-09-01T05:30:00+05:30")],
        ),
        (
            "currency_amount",
            {"value_number": Decimal("2"), "currency": "USD"},
            [
                ("eq", {"amount": "2", "currency": "USD"}),
                ("in", [{"amount": "2", "currency": "USD"}, {"amount": "3", "currency": "EUR"}]),
            ],
        ),
    ],
)
async def test_typed_predicates_do_not_leak_scope_or_old_generations(
    engine: AsyncEngine, kind: str, stored: dict[str, Any], queries: list[tuple[str, Any]]
) -> None:
    company, tenant = uuid7(), uuid7()
    factory = create_session_factory(engine, guarded=True)
    definition = field(kind, validation=ValidationRules(case_sensitive=False))
    if stored.get("value_text") == "HELLO":
        definition = field(kind, validation=ValidationRules(case_sensitive=True))
    if kind == "decimal":
        definition = field(
            kind, validation=ValidationRules.model_validate({"min": "1", "decimal_places": 2})
        )
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            row = CompanyThing(tenant_id=tenant, company_id=company)
            absent = CompanyThing(tenant_id=tenant, company_id=company)
            db.add_all([row, absent])
            await db.flush()
            base = dict(
                tenant_id=tenant,
                company_id=company,
                entity_type="test.company",
                entity_id=row.id,
                field_key="cf_value",
                generation=1,
                **stored,
            )
            db.add(ScalarFixture(**base))
            with unfiltered():
                db.add_all(
                    [
                        ScalarFixture(**{**base, "entity_id": absent.id, "tenant_id": uuid7()}),
                        ScalarFixture(**{**base, "entity_id": absent.id, "company_id": uuid7()}),
                        ScalarFixture(**{**base, "entity_id": absent.id, "generation": 2}),
                    ]
                )
                await db.flush()
        async with factory() as db:
            statement = select(CompanyThing.id).where(CompanyThing.company_id == company)
            for op, value in [*queries, ("is_set", True)]:
                assert list(
                    await db.scalars(statement.where(build(definition, company, op, value)))
                ) == [row.id]
            assert list(
                await db.scalars(statement.where(build(definition, company, "is_set", False)))
            ) == [absent.id]
            if kind == "currency_amount":
                assert (
                    list(
                        await db.scalars(
                            statement.where(
                                build(definition, company, "eq", {"amount": "2", "currency": "EUR"})
                            )
                        )
                    )
                    == []
                )


async def test_membership_exists_never_multiplies_owner_rows(engine: AsyncEngine) -> None:
    company, tenant = uuid7(), uuid7()
    factory = create_session_factory(engine, guarded=True)
    definition = field("multi_select")
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            row = CompanyThing(tenant_id=tenant, company_id=company)
            db.add(row)
            await db.flush()
            for member in ("a", "b"):
                db.add(
                    MemberFixture(
                        tenant_id=tenant,
                        company_id=company,
                        entity_type="test.company",
                        entity_id=row.id,
                        field_key="cf_value",
                        generation=1,
                        member_value=member,
                    )
                )
        async with factory() as db:
            for op in ("has_any", "has_all"):
                assert list(
                    await db.scalars(
                        select(CompanyThing.id).where(build(definition, company, op, ["a", "b"]))
                    )
                ) == [row.id]
            assert (
                list(
                    await db.scalars(
                        select(CompanyThing.id).where(
                            build(definition, company, "has_all", ["a", "missing"])
                        )
                    )
                )
                == []
            )


def test_unreadable_stale_inactive_and_malformed_predicates() -> None:
    company, definition = uuid7(), field()
    with tenant_scope(uuid7()):
        with pytest.raises(PermissionDeniedError):
            build(definition, company, "eq", "hidden", readable=frozenset())
        for modified in [field(is_searchable=False), field(is_active=False), field(key="cf_other")]:
            with pytest.raises(ValidationFailedError):
                build(modified, company, "eq", "x")
        for binding in [
            ReadyIndex(definition, 0, definition_digest(definition)),
            ReadyIndex(definition, True, definition_digest(definition)),
            ReadyIndex(definition, 1, "stale"),
        ]:
            with pytest.raises(ConflictError):
                build(definition, company, "eq", "x", binding=binding)
        from billing_platform.constants import SCOPE_ALL

        with pytest.raises(ValidationFailedError):
            build(definition, SCOPE_ALL, "eq", "x")
        for kind, op, value in [
            ("text", "is_set", 1),
            ("text", "gte", "a"),
            ("text", "has_all", ["a"]),
            ("text", "in", []),
            ("text", "in", "x"),
            ("text", "eq", 1),
            ("text", "eq", "\ufdfa" * 100),
            ("multi_select", "eq", "a"),
            ("multi_select", "has_any", []),
            ("multi_select", "has_any", [1]),
            ("multi_select", "has_all", ["a", "a"]),
        ]:
            with pytest.raises(ValidationFailedError):
                build(field(kind), company, op, value)
