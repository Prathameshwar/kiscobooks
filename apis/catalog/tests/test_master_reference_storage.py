import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.master_references import external_key, normalized_alias
from catalog.models.master_references import MasterAlias, MasterExternalKey


def test_reference_normalization_and_opaque_external_identity() -> None:
    assert normalized_alias("  Stra\u00dfe  Parts ") == ("Stra\u00dfe  Parts", "strasse parts")
    assert normalized_alias("\uff21\uff22\uff23")[1] == "abc"
    assert external_key("000AbC  42") == "000AbC  42"
    for bad in ("", " ", "a\x00b", "\u200b", "a" * 201):
        with pytest.raises(ValidationFailedError):
            external_key(bad)
    for bad in ("", " ", "a\nb", "a" * 101, "\ufdfa" * 100):
        with pytest.raises(ValidationFailedError):
            normalized_alias(bad)


async def test_reference_tables_isolate_tenants_and_keep_company_scoped_claims(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                common = {
                    "tenant_id": tenant,
                    "company_id": company,
                    "entity_type": "catalog.brand",
                    "target_id": uuid7(),
                    "row_version": 1,
                    "is_active": True,
                }
                db.add(
                    MasterAlias(
                        **common, alias="Same", canonical_value="same", normalization_version=1
                    )
                )
                db.add(MasterExternalKey(**common, source_namespace="erp", external_key="0001"))
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (MasterAlias, MasterExternalKey):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert isinstance(rows[0], MasterAlias | MasterExternalKey)
                    assert rows[0].tenant_id == tenant and rows[0].company_id == company
    tenant, company = scopes[0]
    common = {
        "tenant_id": tenant,
        "company_id": company,
        "entity_type": "catalog.brand",
        "target_id": uuid7(),
        "row_version": 1,
        "is_active": True,
    }
    with tenant_scope(tenant), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(
                MasterAlias(**common, alias="SAME", canonical_value="same", normalization_version=1)
            )
            await db.flush()
    with tenant_scope(tenant):
        async with factory.begin() as db:
            db.add(
                MasterAlias(
                    **{**common, "company_id": uuid7()},
                    alias="Same",
                    canonical_value="same",
                    normalization_version=1,
                )
            )
    for invalid in (
        {"entity_type": "catalog.unknown"},
        {"row_version": 0},
        {"normalization_version": 2},
    ):
        with tenant_scope(tenant), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(
                    MasterAlias(
                        **{
                            **common,
                            "alias": "Other",
                            "canonical_value": "other",
                            "normalization_version": 1,
                            **invalid,
                        }
                    )
                )
                await db.flush()
