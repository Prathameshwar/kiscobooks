import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import PrimaryKeyConstraint, Table, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.attributes import AttributeValue
from catalog.models.attributes import (
    AttributeDefinition,
    AttributeOption,
    AttributeSet,
    AttributeSetMember,
    AttributeSetRevision,
)
from catalog.models.commercial import ProductType, ProductTypeRevision
from tests.attribute_factories import seed_attributes


def test_attribute_foreign_keys_have_explicit_supporting_indexes() -> None:
    for model in (
        AttributeDefinition,
        AttributeOption,
        AttributeSet,
        AttributeSetRevision,
        AttributeSetMember,
        ProductTypeRevision,
    ):
        table = model.__table__
        assert isinstance(table, Table)
        indexes = [tuple(column.name for column in index.columns) for index in table.indexes]
        indexes += [
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, PrimaryKeyConstraint | UniqueConstraint)
        ]
        for foreign in table.foreign_key_constraints:
            local = tuple(column.name for column in foreign.columns)
            assert any(index[: len(local)] == local for index in indexes), (
                table.name,
                foreign.name,
            )


async def test_all_attribute_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    companies = (uuid7(), uuid7())
    for tenant, company in zip((tenant_a, tenant_b), companies, strict=True):
        await seed_attributes(factory, tenant, company)
    for tenant, company in zip((tenant_a, tenant_b), companies, strict=True):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (
                    AttributeDefinition,
                    AttributeOption,
                    AttributeSet,
                    AttributeSetRevision,
                    AttributeSetMember,
                ):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert isinstance(
                        rows[0],
                        AttributeDefinition
                        | AttributeOption
                        | AttributeSet
                        | AttributeSetRevision
                        | AttributeSetMember,
                    )
                    assert rows[0].tenant_id == tenant and rows[0].company_id == company


async def test_attribute_type_company_and_representation_constraints(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, other = uuid7(), uuid7()
    own = await seed_attributes(factory, tenant_a, company)
    foreign = await seed_attributes(factory, tenant_a, other)
    common = {"tenant_id": tenant_a, "company_id": company}
    digest, canonical = AttributeValue("TEXT", "Green").canonical()
    option = {
        **common,
        "code": "GREEN",
        "name": "Green",
        "value_type": "TEXT",
        "value_text": "Green",
        "value_hash": digest,
        "canonical_value": canonical,
    }
    for row in (
        AttributeOption(**option, definition_id=foreign["attribute_definition"]),
        AttributeOption(
            **{**option, "value_type": "INTEGER", "value_text": None, "value_integer": 1},
            definition_id=own["attribute_definition"],
        ),
        AttributeOption(**option, definition_id=own["attribute_definition"], value_integer=1),
        AttributeSetRevision(**common, attribute_set_id=foreign["attribute_set"], revision=2),
        AttributeSetMember(
            **common,
            revision_id=foreign["attribute_set_revision"],
            definition_id=own["attribute_definition"],
            position=1,
            is_required=False,
            allow_variant_axis=False,
        ),
        AttributeSetMember(
            **common,
            revision_id=own["attribute_set_revision"],
            definition_id=foreign["attribute_definition"],
            position=1,
            is_required=False,
            allow_variant_axis=False,
        ),
        AttributeDefinition(
            **common,
            code="INVALID",
            name="Invalid",
            value_type="TEXT",
            measurement_dimension="MASS",
        ),
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(row)
                await db.flush()


async def test_product_type_binding_has_a_same_company_database_foreign_key(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, other = uuid7(), uuid7()
    own = await seed_attributes(factory, tenant_a, company)
    foreign = await seed_attributes(factory, tenant_a, other)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            parent = ProductType(
                tenant_id=tenant_a, company_id=company, code="T", name="Type", kind="GOODS"
            )
            db.add(parent)
            await db.flush()
            parent_id = parent.id
        requirements = {
            "tenant_id": tenant_a,
            "company_id": company,
            "product_type_id": parent_id,
            "kind": "GOODS",
            "inventory_modes": ["STOCK"],
            "tracking_modes": ["NONE"],
            "unit_dimensions": ["COUNT"],
            "allow_variants": True,
            "require_brand": False,
            "require_manufacturer": False,
            "require_expiry": False,
        }
        async with factory.begin() as db:
            db.add(
                ProductTypeRevision(
                    **requirements,
                    revision=1,
                    attribute_set_revision_id=own["attribute_set_revision"],
                )
            )
            await db.flush()
        with pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(
                    ProductTypeRevision(
                        **requirements,
                        revision=2,
                        attribute_set_revision_id=foreign["attribute_set_revision"],
                    )
                )
                await db.flush()
