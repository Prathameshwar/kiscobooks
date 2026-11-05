from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import replace
from decimal import Decimal, Inexact, localcontext

import pytest
from billing_platform.db.mixins import TenantMixin
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.exact import RationalConversion
from billing_platform.ids import uuid7
from billing_platform.money import MoneyError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.units import (
    CanonicalRelation,
    FixedBinding,
    QuantityRule,
    UnitDefinition,
    compound_quantity,
    validate_canonical_relations,
    validate_measured_quantity,
)
from catalog.models import PackType, UnitConversion, UnitOfMeasure, UnitTaxCode
from catalog.schemas.units import UnitCreate, UnitTaxCodeInput


def unit(
    company: uuid.UUID, *, dimension: str = "COUNT", places: int = 0, increment: str = "1"
) -> UnitDefinition:
    return UnitDefinition(uuid7(), company, dimension, QuantityRule(places, Decimal(increment)))


def test_compound_packs_and_exact_fractional_conversion() -> None:
    company = uuid7()
    piece, box = unit(company), unit(company, places=2, increment="0.25")
    pack = FixedBinding(uuid7(), box, piece, RationalConversion(12, 1), box.quantity)
    single = FixedBinding(uuid7(), piece, piece, RationalConversion(1, 1), piece.quantity)
    assert pack.convert("0.25") == Decimal("3.0000")
    assert compound_quantity(((pack, "2"), (single, "3"))) == Decimal("27.0000")
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = True
        assert compound_quantity(((pack, "12"), (single, "3"))) == Decimal("147.0000")
    with pytest.raises(MoneyError):
        pack.convert("0.1")
    with pytest.raises(ValidationFailedError):
        replace(pack, fractional_entry=False).convert("0.25")
    with pytest.raises(ValidationFailedError):
        pack.convert("-1")
    with pytest.raises(MoneyError):
        replace(pack, ratio=RationalConversion(1, 3)).convert("1")


def test_all_increments_and_precision_limits_apply() -> None:
    company = uuid7()
    hours = unit(company, dimension="TIME", places=2, increment="0.20")
    binding = FixedBinding(
        uuid7(), hours, hours, RationalConversion(1, 1), QuantityRule(2, Decimal("0.25"))
    )
    assert binding.convert("1") == Decimal("1.0000")
    for value in ("0.20", "0.25", "0.125", "0.0001"):
        with pytest.raises(MoneyError):
            binding.convert(value)
    with pytest.raises(ValidationFailedError):
        replace(binding, quantity=QuantityRule(3, Decimal("0.001")))
    with pytest.raises(ValidationFailedError):
        QuantityRule(0, Decimal("0"))
    with pytest.raises(ValidationFailedError):
        replace(hours, dimension="UNKNOWN")
    with pytest.raises(ValidationFailedError):
        replace(hours, id=uuid.UUID(int=0))


def test_canonical_graph_has_one_direct_same_dimension_root() -> None:
    company = uuid7()
    gram, kilo = unit(company, dimension="MASS"), unit(company, dimension="MASS")
    root = CanonicalRelation(gram, gram, RationalConversion(1, 1))
    child = CanonicalRelation(kilo, gram, RationalConversion(1000, 1))
    validate_canonical_relations((root, child))
    for relations in (
        (child,),
        (root, root),
        (child, CanonicalRelation(gram, kilo, RationalConversion(1, 1000))),
        (root, replace(child, canonical=replace(gram, quantity=QuantityRule(1, Decimal("0.1"))))),
    ):
        with pytest.raises(ValidationFailedError):
            validate_canonical_relations(relations)
    for bad in (unit(uuid7(), dimension="MASS"), unit(company, dimension="COUNT")):
        with pytest.raises(ValidationFailedError):
            CanonicalRelation(kilo, bad, RationalConversion(1, 1))
    with pytest.raises(ValidationFailedError):
        CanonicalRelation(gram, gram, RationalConversion(2, 1))


def test_measured_and_serialized_rules_do_not_invent_stock() -> None:
    company = uuid7()
    sack, kilogram = unit(company), unit(company, dimension="MASS", places=2, increment="0.01")
    assert validate_measured_quantity(
        entered_unit=sack, entered_quantity="1", measured_unit=kilogram, measured_quantity="49.6"
    ) == (Decimal("1"), Decimal("49.6"))
    with pytest.raises(ValidationFailedError):
        validate_measured_quantity(
            entered_unit=sack,
            entered_quantity="0",
            measured_unit=kilogram,
            measured_quantity="49.6",
        )
    with pytest.raises(ValidationFailedError):
        validate_measured_quantity(
            entered_unit=sack,
            entered_quantity="1",
            measured_unit=unit(uuid7()),
            measured_quantity="1",
        )
    for base in (kilogram, unit(uuid7())):
        with pytest.raises(ValidationFailedError):
            FixedBinding(uuid7(), sack, base, RationalConversion(1, 1), sack.quantity)
    with pytest.raises(ValidationFailedError):
        FixedBinding(
            uuid7(),
            kilogram,
            kilogram,
            RationalConversion(1, 1),
            kilogram.quantity,
            serialized_base=True,
        )
    piece = FixedBinding(
        uuid7(), sack, sack, RationalConversion(1, 1), sack.quantity, serialized_base=True
    )
    assert piece.convert("2") == Decimal("2.0000")
    with pytest.raises(MoneyError):
        piece.convert("0.5")
    with pytest.raises(ValidationFailedError):
        compound_quantity(())
    with pytest.raises(ValidationFailedError):
        compound_quantity(((piece, "1"), (piece, "2")))
    other = replace(piece, id=uuid7(), base=unit(company))
    with pytest.raises(ValidationFailedError):
        compound_quantity(((piece, "1"), (other, "2")))


def test_unit_request_rejects_float_and_invalid_precision() -> None:
    values = {
        "code": "KG",
        "name": "Kilogram",
        "symbol": "kg",
        "dimension": "MASS",
        "decimal_places": 3,
        "quantity_increment": "0.001",
    }
    assert UnitCreate.model_validate(values).quantity_increment == Decimal("0.0010")
    for overrides in (
        {"quantity_increment": 0.001},
        {"decimal_places": 0},
        {"on_hand": "1"},
        {"name": "  "},
        {"symbol": "\n"},
    ):
        with pytest.raises((ValidationError, MoneyError)):
            UnitCreate.model_validate({**values, **overrides})
    mapping = {
        "unit_id": uuid7(),
        "jurisdiction": "TEST",
        "official_code": "UNIT",
        "valid_from": dt.date(2026, 1, 1),
    }
    assert UnitTaxCodeInput.model_validate(mapping).valid_to is None
    with pytest.raises(ValidationError):
        UnitTaxCodeInput.model_validate({**mapping, "valid_to": dt.date(2025, 1, 1)})


def unit_row(tenant: uuid.UUID, company: uuid.UUID, code: str = "PCS") -> UnitOfMeasure:
    return UnitOfMeasure(
        id=uuid7(),
        tenant_id=tenant,
        company_id=company,
        code=code,
        name=code,
        symbol=code,
        dimension="COUNT",
        decimal_places=0,
        quantity_increment=Decimal("1"),
    )


async def test_all_unit_tables_are_tenant_isolated(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    for tenant in (tenant_a, tenant_b):
        company = uuid7()
        row = unit_row(tenant, company)
        session.add(row)
        await session.flush()
        session.add(
            UnitConversion(
                id=uuid7(),
                tenant_id=tenant,
                company_id=company,
                from_unit_id=row.id,
                canonical_unit_id=row.id,
                numerator=1,
                denominator=1,
            )
        )
        session.add(
            UnitTaxCode(
                id=uuid7(),
                tenant_id=tenant,
                company_id=company,
                unit_id=row.id,
                jurisdiction="TEST",
                official_code="UNIT",
                valid_from=dt.date(2026, 1, 1),
            )
        )
        session.add(
            PackType(id=uuid7(), tenant_id=tenant, company_id=company, code="BOX", name="Box")
        )
        await session.commit()
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            for model in (UnitOfMeasure, UnitConversion, UnitTaxCode, PackType):
                rows = (await session.scalars(select(model))).all()
                assert len(rows) == 1
                assert isinstance(rows[0], TenantMixin) and rows[0].tenant_id == tenant


async def test_database_rejects_cross_company_conversion_and_duplicate_codes(
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    company, other = uuid7(), uuid7()
    source, target = unit_row(tenant_a, company), unit_row(tenant_a, other)
    session.add_all([source, target])
    await session.commit()
    source_id, target_id = source.id, target.id
    session.add(
        UnitConversion(
            id=uuid7(),
            tenant_id=tenant_a,
            company_id=company,
            from_unit_id=source_id,
            canonical_unit_id=target_id,
            numerator=1,
            denominator=1,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
    session.add(unit_row(tenant_a, company))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


def test_unit_wire_schema_requires_decimal_strings() -> None:
    from catalog.schemas.units import UnitCreate, UnitUpdate

    for model in (UnitCreate, UnitUpdate):
        schema = model.model_json_schema(mode="validation")["properties"]["quantity_increment"]
        assert schema.get("type") == "string"
