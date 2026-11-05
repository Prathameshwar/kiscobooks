from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db.platform_models import IdempotencyKey, Outbox
from billing_platform.db.tenant_context import get_current_tenant, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, IdempotencyConflictError, PermissionDeniedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    canonical_json,
    execute_idempotent,
    has_retained_command,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import emit


class Commands:
    def __init__(self, tenant: uuid.UUID) -> None:
        self.tenant = tenant
        self.company = uuid7()
        self.actor = uuid7()
        self.calls = 0
        self.allowed = True
        self.readable = True
        self.fail = False

    def identity(self, *, key: str = "case-sensitive-Key", body: str = "A") -> CommandIdentity:
        return CommandIdentity(
            self.tenant,
            self.company,
            self.actor,
            "catalog.unit.create",
            key,
            {"code": body, "expected_version": 1},
        )

    async def authorize(self, db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        if not self.allowed:
            raise PermissionDeniedError("permission revoked")

    async def mutate(self, db: AsyncSession) -> CommandReceipt:
        self.calls += 1
        row = emit(
            db,
            tenant_id=self.tenant,
            aggregate_type="test",
            aggregate_id=uuid7(),
            event_type="test.created",
            payload={"test": "only"},
        )
        await db.flush()
        if self.fail:
            raise ValueError("domain rejected command")
        return CommandReceipt(201, {"event_id": str(row.id)})

    async def render(self, db: AsyncSession, receipt: dict[str, Any]) -> dict[str, Any]:
        return {"id": receipt["event_id"], **({"name": "visible"} if self.readable else {})}


async def test_replay_current_read_policy_and_rollback(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    command = Commands(tenant_a)

    async def run() -> Any:
        return await execute_idempotent(
            factory,
            command.identity(),
            authorize=command.authorize,
            mutate=command.mutate,
            render=command.render,
        )

    first = await run()
    assert await has_retained_command(factory, command.identity())
    assert not await has_retained_command(factory, command.identity(key="another-Key"))
    assert not await has_retained_command(factory, Commands(uuid7()).identity())
    command.readable = False
    second = await run()
    assert first.status == second.status == 201
    assert not first.replayed and second.replayed
    assert "name" in first.value and "name" not in second.value
    assert command.calls == 1
    command.allowed = False
    with pytest.raises(PermissionDeniedError):
        await run()
    command.allowed = True
    command.fail = True
    command.company = uuid7()
    with pytest.raises(ValueError):
        await execute_idempotent(
            factory,
            command.identity(key="fail"),
            authorize=command.authorize,
            mutate=command.mutate,
            render=command.render,
        )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len((await db.scalars(select(IdempotencyKey))).all()) == 1
            assert len((await db.scalars(select(Outbox))).all()) == 1
    assert get_current_tenant() is None


async def test_identity_binding_case_sensitive_keys_and_tenant_isolation(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    command = Commands(tenant_a)

    async def run(identity: CommandIdentity) -> None:
        await execute_idempotent(
            factory,
            identity,
            authorize=command.authorize,
            mutate=command.mutate,
            render=command.render,
        )

    await run(command.identity())
    with pytest.raises(IdempotencyConflictError):
        await run(command.identity(body="B"))
    command.actor = uuid7()
    with pytest.raises(IdempotencyConflictError):
        await run(command.identity())
    await run(command.identity(key="case-sensitive-key"))
    command.tenant = tenant_b
    await run(command.identity())
    assert command.calls == 3
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert len((await db.scalars(select(IdempotencyKey))).all()) == 1


async def test_expired_inflight_and_invalid_receipts_fail_closed(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    command = Commands(tenant_a)

    async def run() -> None:
        await execute_idempotent(
            factory,
            command.identity(),
            authorize=command.authorize,
            mutate=command.mutate,
            render=command.render,
        )

    await run()
    for change in ("inflight", "broken", "expired"):
        with tenant_scope(tenant_a):
            async with factory() as db, db.begin():
                row = (await db.scalars(select(IdempotencyKey))).one()
                row.state = "in_progress" if change == "inflight" else "completed"
                if change == "broken":
                    row.response_body = None
                if change == "expired":
                    row.expires_at = utcnow() - dt.timedelta(seconds=1)
        with pytest.raises(ConflictError):
            await run()
    assert command.calls == 1


async def test_timeout_rolls_back_effect_and_claim(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    command = Commands(tenant_a)

    async def slow(db: AsyncSession) -> CommandReceipt:
        receipt = await command.mutate(db)
        await asyncio.sleep(2)
        return receipt

    with pytest.raises(ConflictError):
        await execute_idempotent(
            factory,
            command.identity(),
            authorize=command.authorize,
            mutate=slow,
            render=command.render,
            timeout_seconds=1,
        )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (await db.scalars(select(IdempotencyKey))).all() == []
            assert (await db.scalars(select(Outbox))).all() == []


@pytest.mark.parametrize("value", [1.2, {"x": float("nan")}, {1: "x"}, ("x",), uuid.uuid4()])
def test_canonical_identity_rejects_lossy_values(value: Any) -> None:
    with pytest.raises(ValueError):
        canonical_json(value)


def test_canonical_order_and_limits() -> None:
    assert canonical_json({"b": "2.0000", "a": [True, None, 1]}) == canonical_json(
        {"a": [True, None, 1], "b": "2.0000"}
    )
    with pytest.raises(ValueError):
        canonical_json({"a": "long"}, maximum_bytes=2)
    value: Any = None
    for _ in range(35):
        value = [value]
    with pytest.raises(ValueError):
        canonical_json(value)
    with pytest.raises(ValueError):
        CommandReceipt(400, {})


async def test_command_boundary_validation_and_lock_errors(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from sqlalchemy.exc import OperationalError

    from billing_platform.errors import ValidationFailedError

    command = Commands(tenant_a)
    for operation, key in (("INVALID", "key"), ("valid", "space in key")):
        with pytest.raises((ValueError, ValidationFailedError)):
            CommandIdentity(tenant_a, command.company, command.actor, operation, key, {})
    with pytest.raises(ValueError):
        CommandIdentity(uuid.UUID(int=0), command.company, command.actor, "valid", "key", {})
    for arguments in ({"retention": dt.timedelta(seconds=1)}, {"timeout_seconds": 0}):
        with pytest.raises(ValueError):
            await execute_idempotent(
                factory,
                command.identity(),
                authorize=command.authorize,
                mutate=command.mutate,
                render=command.render,
                **arguments,
            )
    for code in (1205, 1213, 3572, "database is locked", 9999):

        async def failure(db: AsyncSession, failure_code: int | str = code) -> CommandReceipt:
            raise OperationalError("synthetic fault", {}, Exception(failure_code))

        with pytest.raises(OperationalError if code == 9999 else ConflictError):
            await execute_idempotent(
                factory,
                command.identity(),
                authorize=command.authorize,
                mutate=failure,
                render=command.render,
            )


def test_mysql_claim_only_preserves_existing_identity() -> None:
    from sqlalchemy.dialects import mysql

    from billing_platform.idempotency import claim_statement

    statement = claim_statement("mysql", {"id": uuid7(), "key_value": "bound-parameter"})
    sql = str(statement.compile(dialect=mysql.dialect()))
    assert "ON DUPLICATE KEY UPDATE id = idempotency_key.id" in sql
    assert "bound-parameter" not in sql
    assert "response_body =" not in sql
    with pytest.raises(ValueError):
        claim_statement("unsupported", {})


async def test_concurrent_same_key_commits_one_effect(tmp_path: Path, tenant_a: uuid.UUID) -> None:
    from billing_platform.db.base import Base
    from billing_platform.db.session import create_engine, create_session_factory

    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'commands.db').as_posix()}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        command = Commands(tenant_a)
        first_claimed = asyncio.Event()
        second_authorized = asyncio.Event()

        async def first_mutation(db: AsyncSession) -> CommandReceipt:
            first_claimed.set()
            await second_authorized.wait()
            return await command.mutate(db)

        async def second_authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
            second_authorized.set()
            await command.authorize(db, receipt)

        first = asyncio.create_task(
            execute_idempotent(
                factory,
                command.identity(),
                authorize=command.authorize,
                mutate=first_mutation,
                render=command.render,
            )
        )
        await first_claimed.wait()
        second = asyncio.create_task(
            execute_idempotent(
                factory,
                command.identity(),
                authorize=second_authorize,
                mutate=command.mutate,
                render=command.render,
            )
        )
        results = await asyncio.gather(first, second)
        assert sorted(result.replayed for result in results) == [False, True]
        assert results[0].value == results[1].value and command.calls == 1
        with tenant_scope(tenant_a):
            async with factory() as db:
                assert len((await db.scalars(select(IdempotencyKey))).all()) == 1
                assert len((await db.scalars(select(Outbox))).all()) == 1
    finally:
        await engine.dispose()
