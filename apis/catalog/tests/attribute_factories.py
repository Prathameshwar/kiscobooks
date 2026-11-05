import uuid

from billing_platform.db import tenant_scope
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.attributes import AttributeValue
from catalog.models.attributes import (
    AttributeDefinition,
    AttributeOption,
    AttributeSet,
    AttributeSetMember,
    AttributeSetRevision,
)
from tests.test_api import headers
from tests.test_classification_api import setup_source


async def auth(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    version: int = 2,
    facts: tuple[SnapshotRecord, ...] | None = None,
) -> dict[str, str]:
    await setup_source(factory, tenant, company, user, version=version, facts=facts)
    return headers(
        company,
        tenant=tenant,
        user=user,
        permission=[
            *(
                name + suffix
                for name in (
                    "attribute_definition",
                    "attribute_option",
                    "attribute_set",
                    "product_type",
                    "unit",
                )
                for suffix in (".read", ".manage")
            ),
            "attribute_set.publish",
            "product_type.publish",
        ],
    )


async def seed_attributes(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> dict[str, uuid.UUID]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            common = {"tenant_id": tenant, "company_id": company}
            definition = AttributeDefinition(
                **common, code="COLOUR", name="Colour", value_type="TEXT", is_variant_capable=True
            )
            template = AttributeSet(**common, code="CLOTHING", name="Clothing")
            db.add_all([definition, template])
            await db.flush()
            digest, canonical = AttributeValue("TEXT", "Blue").canonical()
            option = AttributeOption(
                **common,
                definition_id=definition.id,
                code="BLUE",
                name="Blue",
                value_type="TEXT",
                value_text="Blue",
                value_hash=digest,
                canonical_value=canonical,
            )
            revision = AttributeSetRevision(**common, attribute_set_id=template.id, revision=1)
            db.add_all([option, revision])
            await db.flush()
            member = AttributeSetMember(
                **common,
                revision_id=revision.id,
                definition_id=definition.id,
                position=0,
                is_required=True,
                allow_variant_axis=True,
            )
            db.add(member)
            await db.flush()
            return {
                row.__tablename__: row.id
                for row in (definition, template, option, revision, member)
            }
