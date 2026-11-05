"""Opt-in native concurrency proof on a validated disposable local schema."""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.base import Base
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from catalog.models.classification import ItemGroup
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.tasks.company_product_defaults import ensure_product_defaults
from tests.test_unit_defaults import provision

pytestmark = pytest.mark.mysql


@pytest_asyncio.fixture
async def native_defaults_factory():
    configured = os.getenv("QA_MYSQL_SERVER_URL")
    if not configured:
        pytest.skip("Set QA_MYSQL_SERVER_URL to the dedicated local test server")
    server = make_url(configured)
    if server.database or server.host not in {"127.0.0.1", "localhost"} or server.port != 13396:
        raise ValueError("Defaults tests require the dedicated 13396 server and no database")
    schema = "company_defaults_test_" + uuid.uuid4().hex
    admin = create_engine(server.render_as_string(hide_password=False))
    owner = None
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f"CREATE DATABASE `{schema}`"))
        owner = create_engine(server.set(database=schema).render_as_string(hide_password=False))
        async with owner.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield create_session_factory(owner, guarded=True)
    finally:
        if owner is not None:
            await owner.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP DATABASE IF EXISTS `{schema}`"))
        await admin.dispose()


async def test_concurrent_native_catchup_is_unique_and_preserves_identities(
    native_defaults_factory,
):
    from billing_platform.ids import uuid7

    factory = native_defaults_factory
    tenant, company = uuid7(), uuid7()
    await provision(factory, tenant, company)

    async def create():
        with tenant_scope(tenant):
            async with factory.begin() as db:
                return (await ensure_product_defaults(db, company)).created_records

    assert sorted(await asyncio.gather(create(), create())) == [0, 4]
    with tenant_scope(tenant):
        async with factory.begin() as db:
            types = list(await db.scalars(select(ProductType)))
            groups = list(await db.scalars(select(ItemGroup)))
            revisions = list(await db.scalars(select(ProductTypeRevision)))
            assert len(types) == len(groups) == len(revisions) == 1
            assert types[0].code == groups[0].code == "DEFAULT"
            identities = (types[0].id, groups[0].id, revisions[0].id)
            assert (await ensure_product_defaults(db, company)).created_records == 0
            assert identities == (types[0].id, groups[0].id, revisions[0].id)
    with tenant_scope(uuid7()):
        async with factory.begin() as db:
            assert list(await db.scalars(select(ProductType))) == []


async def test_native_named_default_reuse_is_case_insensitive(native_defaults_factory):
    from billing_platform.ids import uuid7

    factory = native_defaults_factory
    tenant, company = uuid7(), uuid7()
    await provision(factory, tenant, company, inventory=False)
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            product_type = (await db.scalars(select(ProductType))).one()
            group = (await db.scalars(select(ItemGroup))).one()
            product_type.code, product_type.name = "MY_TYPE", "default"
            group.code, group.name = "MY_GROUP", "DEFAULT"
        async with factory.begin() as db:
            assert (await ensure_product_defaults(db, company)).created_records == 0
            assert len(list(await db.scalars(select(ProductType)))) == 1
            assert len(list(await db.scalars(select(ItemGroup)))) == 1
