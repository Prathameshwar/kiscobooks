import uuid
from typing import Any, Literal

import pytest
from billing_platform.custom_fields import CustomDefinition, ValidationRules
from billing_platform.db.session import create_session_factory
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.models.custom_fields import CustomFieldSequence, CustomFieldUniqueClaim
from catalog.tasks.custom_fields import allocate_sequence, reserve_claims


def definitions(scope: Literal["company", "tenant"] = "company") -> tuple[CustomDefinition, ...]:
    return (
        CustomDefinition(
            key="cf_code",
            data_type="text",
            is_searchable=True,
            validation=ValidationRules(unique_within=scope, case_sensitive=False),
        ),
    )


async def test_unique_claims_company_tenant_boundaries_and_rollback(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    tenant, other, company, second_company, owner = uuid7(), uuid7(), uuid7(), uuid7(), uuid7()
    base: dict[str, Any] = {
        "company_id": company,
        "entity_type": "catalog.item",
        "entity_id": owner,
        "definitions": definitions(),
        "values": {"cf_code": "ABC"},
    }
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            await reserve_claims(db, **base)
        async with factory() as db, db.begin():
            await reserve_claims(db, **{**base, "values": {"cf_code": "abc"}})
            assert len(list(await db.scalars(select(CustomFieldUniqueClaim)))) == 1
        with pytest.raises(ConflictError):
            async with factory() as db, db.begin():
                await reserve_claims(db, **{**base, "entity_id": uuid7()})
        async with factory() as db, db.begin():
            await reserve_claims(db, **{**base, "company_id": second_company, "entity_id": uuid7()})
        with pytest.raises(RuntimeError):
            async with factory() as db, db.begin():
                await reserve_claims(db, **{**base, "values": {"cf_code": "rolled-back"}})
                raise RuntimeError("domain failed")
        async with factory() as db:
            rows = list(await db.scalars(select(CustomFieldUniqueClaim)))
            assert len(rows) == 2
            assert all(b"rolled-back" not in row.canonical_value for row in rows)
    with tenant_scope(other):
        async with factory() as db, db.begin():
            assert list(await db.scalars(select(CustomFieldUniqueClaim))) == []
            await reserve_claims(db, **base)


async def test_tenant_claims_and_explicit_hash_collision(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    base: dict[str, Any] = {
        "company_id": uuid7(),
        "entity_type": "catalog.item",
        "entity_id": uuid7(),
        "definitions": definitions("tenant"),
        "values": {"cf_code": "same"},
    }
    with tenant_scope(uuid7()):
        async with factory() as db, db.begin():
            await reserve_claims(db, **base)
        with pytest.raises(ConflictError):
            async with factory() as db, db.begin():
                await reserve_claims(db, **{**base, "company_id": uuid7(), "entity_id": uuid7()})
        async with factory() as db, db.begin():
            row = (await db.scalars(select(CustomFieldUniqueClaim))).one()
            row.canonical_value = b"simulated-different-content-same-hash"
        with pytest.raises(ConflictError, match="collision"):
            async with factory() as db, db.begin():
                await reserve_claims(db, **base)


async def test_sequences_reset_scope_retention_and_rollback(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    base: dict[str, Any] = {
        "company_id": uuid7(),
        "entity_type": "catalog.item",
        "field_key": "cf_number",
        "cycle_key": "",
        "prefix": "IT-",
        "padding": 4,
        "start": 1,
    }
    with tenant_scope(uuid7()):
        async with factory() as db, db.begin():
            assert await allocate_sequence(db, **base) == "IT-0001"
        with pytest.raises(RuntimeError):
            async with factory() as db, db.begin():
                assert await allocate_sequence(db, **base) == "IT-0002"
                raise RuntimeError("domain rejected")
        async with factory() as db, db.begin():
            assert await allocate_sequence(db, **base) == "IT-0002"
            assert await allocate_sequence(db, **{**base, "cycle_key": "2027"}) == "IT-0001"
        async with factory() as db, db.begin():
            row = (
                await db.scalars(
                    select(CustomFieldSequence).where(CustomFieldSequence.cycle_key == "")
                )
            ).one()
            row.next_value = 2**63 - 1
        with pytest.raises(ConflictError):
            async with factory() as db, db.begin():
                await allocate_sequence(db, **base)
    with tenant_scope(uuid7()):
        async with factory() as db:
            assert list(await db.scalars(select(CustomFieldSequence))) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"company_id": uuid.UUID(int=0)},
        {"entity_type": "billing.party"},
        {"field_key": "unsafe"},
        {"cycle_key": "x" * 41},
        {"cycle_key": "2026-13"},
        {"padding": 0},
        {"start": True},
        {"prefix": "\n"},
    ],
)
async def test_sequence_validation(engine: AsyncEngine, changes: dict[str, Any]) -> None:
    factory = create_session_factory(engine, guarded=True)
    base: dict[str, Any] = {
        "company_id": uuid7(),
        "entity_type": "catalog.item",
        "field_key": "cf_number",
        "cycle_key": "",
        "prefix": "IT-",
        "padding": 4,
        "start": 1,
    }
    with tenant_scope(uuid7()):
        async with factory() as db, db.begin():
            with pytest.raises(ValidationFailedError):
                await allocate_sequence(db, **{**base, **changes})


async def test_unreviewed_uniqueness_scope_change_is_rejected(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    base: dict[str, Any] = {
        "company_id": uuid7(),
        "entity_type": "catalog.item",
        "entity_id": uuid7(),
        "definitions": definitions("tenant"),
        "values": {"cf_code": "same"},
    }
    with tenant_scope(uuid7()):
        async with factory() as db, db.begin():
            await reserve_claims(db, **base)
        with pytest.raises(ConflictError, match="scope"):
            async with factory() as db, db.begin():
                await reserve_claims(db, **{**base, "definitions": definitions("company")})
        async with factory() as db:
            assert len(list(await db.scalars(select(CustomFieldUniqueClaim)))) == 1


async def test_typed_indexes_members_generations_and_tenant_scope(engine: AsyncEngine) -> None:
    from decimal import Decimal

    from billing_platform.custom_fields import Choice

    from catalog.models.custom_fields import CustomFieldValueIndex, CustomFieldValueMember
    from catalog.tasks.custom_fields import replace_indexes

    factory = create_session_factory(engine, guarded=True)
    defs = tuple(
        CustomDefinition.model_validate(
            {
                "key": "cf_" + kind,
                "data_type": kind,
                "is_searchable": True,
                **(
                    {
                        "choices": (
                            Choice(value="a", label="A"),
                            Choice(value="A", label="Capital A"),
                        )
                    }
                    if kind == "multi_select"
                    else {}
                ),
            }
        )
        for kind in [
            "text",
            "decimal",
            "integer",
            "date",
            "datetime",
            "boolean",
            "currency_amount",
            "multi_select",
        ]
    )
    values = {
        "cf_text": "Name",
        "cf_decimal": "1.25",
        "cf_integer": 4,
        "cf_date": "2026-01-01",
        "cf_datetime": "2026-01-01T00:00:00+00:00",
        "cf_boolean": False,
        "cf_currency_amount": {"amount": "2.5", "currency": "USD"},
        "cf_multi_select": ["a", "A"],
    }
    base: dict[str, Any] = {
        "company_id": uuid7(),
        "entity_type": "catalog.item",
        "entity_id": uuid7(),
        "definitions": defs,
        "values": values,
        "generations": {d.key: (1, 2) for d in defs},
    }
    tenant = uuid7()
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            await replace_indexes(db, **base)
        async with factory() as db:
            indexed = list(await db.scalars(select(CustomFieldValueIndex)))
            assert len(indexed) == 14
            assert next(
                row for row in indexed if row.field_key == "cf_decimal"
            ).value_number == Decimal("1.2500")
            assert next(row for row in indexed if row.field_key == "cf_boolean").value_bool is False
            assert len(list(await db.scalars(select(CustomFieldValueMember)))) == 4
        with pytest.raises(RuntimeError):
            async with factory() as db, db.begin():
                await replace_indexes(db, **{**base, "values": {}})
                raise RuntimeError("domain rollback")
        async with factory() as db, db.begin():
            assert len(list(await db.scalars(select(CustomFieldValueIndex)))) == 14
            await replace_indexes(
                db, **{**base, "values": {}, "generations": {d.key: (2,) for d in defs}}
            )
        async with factory() as db:
            assert len(list(await db.scalars(select(CustomFieldValueIndex)))) == 7
            assert len(list(await db.scalars(select(CustomFieldValueMember)))) == 2
        with pytest.raises(ConflictError):
            async with factory() as db, db.begin():
                await replace_indexes(db, **{**base, "generations": {}})
    with tenant_scope(uuid7()):
        async with factory() as db:
            assert list(await db.scalars(select(CustomFieldValueIndex))) == []
            assert list(await db.scalars(select(CustomFieldValueMember))) == []


async def test_claim_release_inactive_retention_and_new_sequence_rollback(
    engine: AsyncEngine,
) -> None:
    factory = create_session_factory(engine, guarded=True)
    base: dict[str, Any] = {
        "company_id": uuid7(),
        "entity_type": "catalog.item",
        "entity_id": uuid7(),
        "definitions": definitions(),
        "values": {"cf_code": "first"},
    }
    with tenant_scope(uuid7()):
        async with factory() as db, db.begin():
            await reserve_claims(db, **base)
            await reserve_claims(db, **{**base, "values": {"cf_code": "second"}})
            assert len(list(await db.scalars(select(CustomFieldUniqueClaim)))) == 1
        inactive = tuple(d.model_copy(update={"is_active": False}) for d in definitions())
        async with factory() as db, db.begin():
            await reserve_claims(db, **{**base, "definitions": inactive, "values": {}})
            assert len(list(await db.scalars(select(CustomFieldUniqueClaim)))) == 1
        async with factory() as db, db.begin():
            await reserve_claims(db, **{**base, "values": {}})
            assert list(await db.scalars(select(CustomFieldUniqueClaim))) == []
        with pytest.raises(RuntimeError):
            async with factory() as db, db.begin():
                await allocate_sequence(
                    db,
                    company_id=base["company_id"],
                    entity_type="catalog.item",
                    field_key="cf_number",
                    cycle_key="",
                    prefix="",
                    padding=1,
                    start=1,
                )
                raise RuntimeError("rollback initial sequence")
        async with factory() as db:
            assert list(await db.scalars(select(CustomFieldSequence))) == []


async def test_custom_expansion_and_owner_bounds_fail_before_writing(engine: AsyncEngine) -> None:
    from billing_platform.custom_fields import Choice

    from catalog.tasks.custom_fields import replace_indexes

    factory = create_session_factory(engine, guarded=True)
    base: dict[str, Any] = {
        "company_id": uuid7(),
        "entity_type": "catalog.item",
        "entity_id": uuid7(),
        "definitions": definitions(),
        "values": {"cf_code": "x"},
    }
    with tenant_scope(uuid7()):
        async with factory() as db, db.begin():
            with pytest.raises(ValidationFailedError):
                await replace_indexes(
                    db,
                    **{
                        **base,
                        "values": {"cf_code": "\ufdfa" * 100},
                        "generations": {"cf_code": (1,)},
                    },
                )
            with pytest.raises(ValidationFailedError):
                await reserve_claims(db, **{**base, "entity_id": uuid.UUID(int=0)})
            with pytest.raises(ConflictError, match="compatible value contract"):
                await reserve_claims(db, **{**base, "values": {"cf_code": "x" * 4096}})
            # Valid raw text can exceed the claim's byte bound after Unicode normalization.
            with pytest.raises(ValidationFailedError):
                await reserve_claims(db, **{**base, "values": {"cf_code": "\ufdfa" * 200}})
            with pytest.raises(ValidationFailedError):
                await replace_indexes(
                    db, **{**base, "entity_id": uuid.UUID(int=0), "generations": {"cf_code": (1,)}}
                )
            await replace_indexes(
                db,
                **{
                    **base,
                    "definitions": tuple(
                        d.model_copy(update={"is_searchable": False}) for d in definitions()
                    ),
                    "generations": {},
                },
            )
            multi = tuple(
                CustomDefinition(
                    key="cf_members_" + chr(97 + i),
                    data_type="multi_select",
                    is_searchable=True,
                    choices=tuple(Choice(value=str(n), label=str(n)) for n in range(100)),
                )
                for i in range(11)
            )
            with pytest.raises(ValidationFailedError):
                await replace_indexes(
                    db,
                    **{
                        **base,
                        "definitions": multi,
                        "values": {d.key: [str(n) for n in range(100)] for d in multi},
                        "generations": {d.key: (1,) for d in multi},
                    },
                )


async def test_fiscal_sequence_is_unavailable_without_owner_source(engine: AsyncEngine) -> None:
    from catalog.domain.sources import SourceUnavailableError

    factory = create_session_factory(engine, guarded=True)
    with tenant_scope(uuid7()):
        async with factory() as db, db.begin():
            with pytest.raises(SourceUnavailableError):
                await allocate_sequence(
                    db,
                    company_id=uuid7(),
                    entity_type="catalog.item",
                    field_key="cf_number",
                    cycle_key=str(uuid7()),
                    prefix="",
                    padding=1,
                    start=1,
                )
