"""Regression coverage for writes and identity-map tenant isolation."""

from typing import Any

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.session import create_session_factory
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from tests.models import SharedThing, TenantThing


async def test_foreign_tenant_insert_is_rejected(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    with tenant_scope(uuid7()):
        async with factory() as db:
            db.add(TenantThing(tenant_id=uuid7(), name="foreign"))
            with pytest.raises(TenantContextError):
                await db.flush()


async def test_reused_session_cannot_return_cached_other_tenant(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    first, second = uuid7(), uuid7()
    async with factory() as db:
        with tenant_scope(first):
            row = TenantThing(tenant_id=first, name="private")
            db.add(row)
            await db.commit()
            assert await db.get(TenantThing, row.id) is row
        with tenant_scope(second), pytest.raises(TenantContextError):
            await db.get(TenantThing, row.id)


async def test_bulk_update_cannot_escape_tenant(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    with tenant_scope(uuid7()):
        async with factory() as db:
            with pytest.raises(TenantContextError):
                await db.execute(update(TenantThing).values(name="unauthorized"))


@pytest.mark.parametrize("action", ["update", "delete", "move", "shared", "raw", "missing"])
async def test_guarded_write_paths_and_context(engine: AsyncEngine, action: str) -> None:
    factory = create_session_factory(engine, guarded=True)
    owner = uuid7()
    async with factory() as db:
        with unfiltered():
            row = TenantThing(tenant_id=owner, name="kept")
            shared = SharedThing(tenant_id=SCOPE_ALL, key="system")
            db.add_all([row, shared])
            await db.commit()
        if action == "missing":
            db.add(TenantThing(tenant_id=owner, name="unscoped"))
            with pytest.raises(TenantContextError):
                await db.flush()
            return
        with tenant_scope(owner):
            with pytest.raises(TenantContextError):
                if action == "raw":
                    await db.execute(text("SELECT 1"))
                elif action == "delete":
                    await db.execute(delete(TenantThing))
                elif action == "update":
                    await db.execute(update(TenantThing).values(name="bulk"))
                else:
                    if action == "move":
                        row.tenant_id = uuid7()
                    else:
                        shared.key = "tampered"
                    await db.flush()


async def test_bootstrap_identity_map_cannot_leak_foreign_row(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    async with factory() as db:
        with unfiltered():
            row = TenantThing(tenant_id=uuid7(), name="private")
            db.add(row)
            await db.commit()
        with tenant_scope(uuid7()):
            assert await db.get(TenantThing, row.id) is None
            assert list(await db.scalars(select(TenantThing))) == []


async def test_own_row_update_commit_and_delete(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    with tenant_scope(uuid7()):
        from billing_platform.db.tenant_context import require_current_tenant

        async with factory() as db:
            row = TenantThing(tenant_id=require_current_tenant(), name="before")
            db.add(row)
            await db.commit()
            row.name = "after"
            await db.commit()
            reloaded = await db.get(TenantThing, row.id)
            assert reloaded is not None and reloaded.name == "after"
            await db.delete(row)
            await db.commit()
            assert await db.get(TenantThing, row.id) is None


async def test_nil_tenant_and_statement_bypass_are_rejected(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    async with factory() as db:
        with tenant_scope(SCOPE_ALL), pytest.raises(TenantContextError):
            await db.execute(select(TenantThing))
        with tenant_scope(uuid7()), pytest.raises(TenantContextError):
            await db.execute(select(TenantThing).execution_options(skip_tenant_filter=True))


async def test_exempt_rows_and_self_tenant_guard(engine: AsyncEngine) -> None:
    from tests.models import ExemptThing, RootLike

    factory = create_session_factory(engine, guarded=True)
    owner = uuid7()
    async with factory() as db:
        db.add(ExemptThing(code="US"))
        await db.commit()
        assert (await db.scalars(select(ExemptThing))).one().code == "US"
        with tenant_scope(owner):
            db.add(RootLike(id=owner, name="own root"))
            await db.commit()
            assert await db.get(RootLike, owner) is not None
        with unfiltered():
            assert await db.get(RootLike, owner) is not None


async def test_ownership_history_cannot_be_laundered(engine: AsyncEngine) -> None:
    from tests.models import CompanyThing

    factory = create_session_factory(engine, guarded=True)
    owner = uuid7()
    async with factory() as db:
        with unfiltered():
            row = CompanyThing(tenant_id=uuid7(), company_id=uuid7())
            db.add(row)
            await db.commit()
        with tenant_scope(owner):
            row.tenant_id = owner
            with pytest.raises(TenantContextError):
                await db.flush()


async def test_core_alias_cannot_hide_foreign_rows_in_an_orm_select(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    owner = uuid7()
    async with factory() as db:
        with unfiltered():
            db.add_all(
                [
                    TenantThing(tenant_id=owner, name="public"),
                    TenantThing(tenant_id=uuid7(), name="private"),
                ]
            )
            await db.commit()
        raw = TenantThing.__table__.alias("raw")
        with tenant_scope(owner), pytest.raises(TenantContextError):
            await db.execute(select(TenantThing.id, raw.c.name).join(raw, raw.c.id == raw.c.id))


async def test_guarded_orm_alias_join_and_nested_select_remain_filtered(
    engine: AsyncEngine,
) -> None:
    from sqlalchemy import literal_column, true
    from sqlalchemy.orm import aliased

    factory = create_session_factory(engine, guarded=True)
    owner = uuid7()
    async with factory() as db:
        with unfiltered():
            db.add_all(
                [
                    TenantThing(tenant_id=owner, name="public"),
                    TenantThing(tenant_id=uuid7(), name="private"),
                ]
            )
            await db.commit()
        alias = aliased(TenantThing)
        with tenant_scope(owner):
            assert list(await db.scalars(select(alias.name))) == ["public"]
            result = await db.execute(select(TenantThing.name, alias.name).join(alias, true()))
            assert [tuple(pair) for pair in result] == [("public", "public")]
            query = select(TenantThing.name).where(
                select(alias.id).where(alias.id == TenantThing.id).exists()
            )
            assert list(await db.scalars(query)) == ["public"]
            subset = select(alias.id).subquery()
            scalar_result = await db.scalars(
                select(TenantThing.name).join(subset, subset.c.id == TenantThing.id)
            )
            assert list(scalar_result) == ["public"]
            unsafe_queries: list[Any] = [
                select(TenantThing.id).where(text("1=1")),
                select(TenantThing.id, literal_column("name")),
                select(TenantThing.id).where(select(TenantThing.__table__.c.id).exists()),
            ]
            for unsafe in unsafe_queries:
                with pytest.raises(TenantContextError):
                    await db.execute(unsafe)
