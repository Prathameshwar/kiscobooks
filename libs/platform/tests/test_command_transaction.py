import asyncio
import uuid
from contextlib import AbstractAsyncContextManager
from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.command_transaction import command_transaction
from billing_platform.db.platform_models import IdempotencyKey, Outbox
from billing_platform.db.tenant_context import get_current_tenant, tenant_scope
from billing_platform.errors import PermissionDeniedError
from billing_platform.idempotency import execute_idempotent
from billing_platform.ids import uuid7
from tests.test_command_execution import Commands


async def test_aggregate_rollback_preview_and_receipt_replay(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    command = Commands(tenant_a)

    async def run(key: str) -> None:
        await execute_idempotent(
            factory,
            command.identity(key=key),
            authorize=command.authorize,
            mutate=command.mutate,
            render=command.render,
        )

    def transaction() -> AbstractAsyncContextManager[AsyncSession]:
        return command_transaction(
            factory, tenant_id=tenant_a, company_id=command.company, actor_id=command.actor
        )

    with pytest.raises(ValueError, match="domain"):
        async with transaction():
            await run("first")
            command.fail = True
            await run("second")
    command.fail = False
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert not list(await db.scalars(select(Outbox)))
            assert not list(await db.scalars(select(IdempotencyKey)))
    async with transaction() as db:
        preview = await db.begin_nested()
        await run("first")
        await preview.rollback()
        assert not list(await db.scalars(select(Outbox)))
        await run("first")
        await run("first")
        assert len(list(await db.scalars(select(Outbox)))) == 1
        command.allowed = False
        with pytest.raises(PermissionDeniedError):
            await run("first")
    assert get_current_tenant() is None
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(Outbox)))) == 1
            assert len(list(await db.scalars(select(IdempotencyKey)))) == 1


async def test_participation_rejects_scope_factory_and_inherited_task(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    command = Commands(tenant_a)
    async with command_transaction(
        factory, tenant_id=tenant_a, company_id=command.company, actor_id=command.actor
    ):
        for identity in (
            replace(command.identity(), tenant_id=uuid7()),
            replace(command.identity(), company_id=uuid7()),
            replace(command.identity(), actor_id=uuid7()),
        ):
            with pytest.raises(RuntimeError, match="cannot join"):
                await execute_idempotent(
                    factory,
                    identity,
                    authorize=command.authorize,
                    mutate=command.mutate,
                    render=command.render,
                )
        with pytest.raises(RuntimeError, match="cannot join"):
            await asyncio.create_task(
                execute_idempotent(
                    factory,
                    command.identity(),
                    authorize=command.authorize,
                    mutate=command.mutate,
                    render=command.render,
                )
            )
        with pytest.raises(RuntimeError, match="cannot join"):
            await execute_idempotent(
                async_sessionmaker(bind=factory.kw["bind"]),
                command.identity(),
                authorize=command.authorize,
                mutate=command.mutate,
                render=command.render,
            )
        with pytest.raises(ValueError, match="independent"):
            async with command_transaction(
                factory, tenant_id=tenant_a, company_id=command.company, actor_id=command.actor
            ):
                pytest.fail("nested owner was accepted")
    with pytest.raises(ValueError, match="real company"):
        async with command_transaction(
            factory, tenant_id=tenant_a, company_id=uuid.UUID(int=0), actor_id=command.actor
        ):
            pytest.fail("zero company was accepted")
