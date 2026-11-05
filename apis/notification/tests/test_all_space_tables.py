"""Every notification-owned table must hide both foreign tenants and foreign spaces."""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.base import Base
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.ids import uuid7
from sqlalchemy import JSON, Boolean, Date, Integer, LargeBinary, String, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine

from notification.metadata import TABLES
from notification.ownership import SpaceMixin, session_factory, space_scope


async def test_every_owned_table_enforces_tenant_and_space(engine: AsyncEngine) -> None:
    models = {
        mapper.local_table.name: mapper.class_
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, SpaceMixin)
    }
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name in models and table.name in TABLES
    ]
    tenant_a, tenant_b, platform = uuid7(), uuid7(), uuid7()
    scopes = [(tenant_a, tenant_a), (tenant_b, tenant_b), (tenant_a, platform)]
    ids = {(index, table.name): uuid7() for index in range(3) for table in tables}
    rows: dict[tuple[int, str], Any] = {}
    factory = session_factory(engine)
    async with factory() as db:
        # Fixture provisioning deliberately creates three independent owners.
        with unfiltered():
            for table in tables:
                for index, (tenant, space) in enumerate(scopes):
                    values: dict[str, Any] = {"tenant_id": tenant, "space_id": space}
                    for column in table.columns:
                        name = column.name
                        if name in values:
                            continue
                        if name == "id":
                            values[name] = ids[index, table.name]
                            continue
                        targets = [
                            fk for fk in column.foreign_keys if fk.column.table.name in models
                        ]
                        if targets:
                            target = targets[0].column.table.name
                            values[name] = ids[index, target]
                            continue
                        if column.nullable or column.default is not None:
                            continue
                        kind = column.type
                        if isinstance(kind, Uuid7):
                            values[name] = uuid7()
                        elif isinstance(kind, UtcDateTime):
                            values[name] = dt.datetime.now(dt.UTC)
                        elif isinstance(kind, Boolean):
                            values[name] = True
                        elif isinstance(kind, Integer):
                            values[name] = index + 1
                        elif isinstance(kind, LargeBinary):
                            values[name] = hashlib.sha256(f"{table.name}:{index}".encode()).digest()
                        elif isinstance(kind, JSON):
                            values[name] = {}
                        elif isinstance(kind, Date):
                            values[name] = dt.date.today()
                        elif isinstance(kind, String):
                            values[name] = (f"{index}-{name}").ljust(43, "x")[: kind.length or 43]
                        else:
                            raise AssertionError(f"missing fixture factory for {table.name}.{name}")
                    row = models[table.name](**values)
                    db.add(row)
                    await db.flush()
                    rows[index, table.name] = row
            await db.commit()
    for index, (tenant, space) in enumerate(scopes):
        with tenant_scope(tenant), space_scope(space):
            async with factory() as db:
                for table in tables:
                    model = models[table.name]
                    result = list(await db.scalars(select(model)))
                    assert len(result) == 1, table.name
                    assert result[0].tenant_id == tenant and result[0].space_id == space
                    foreign = rows[(index + 1) % 3, table.name]
                    identity = tuple(getattr(foreign, c.name) for c in inspect(model).primary_key)
                    assert await db.get(model, identity) is None, table.name
