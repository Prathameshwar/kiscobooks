"""One built-in location/policy provisioner for authorized commands and enrollment."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar

from billing_platform.db.base import Base
from billing_platform.db.types import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.warehouses import MAIN_CODE, TRANSIT_CODE, assert_code_available, assert_kind
from catalog.models.warehouses import (
    DEFAULT_POINTERS,
    CompanyWarehouseConfiguration,
    Warehouse,
    WarehouseOperationPolicyRevision,
)

Row = TypeVar("Row", bound=Base)


class Creator(Protocol):
    async def __call__(self, model: type[Row], /, **values: Any) -> Row: ...


async def locations(
    db: AsyncSession, company: uuid.UUID, *, timezone: str, source_version: int, create: Creator
) -> CompanyWarehouseConfiguration:
    config = await db.scalar(
        select(CompanyWarehouseConfiguration).where(
            CompanyWarehouseConfiguration.company_id == company,
        )
    )
    if config is not None:
        return config
    builtins = []
    for code, name, kind, zone in (
        (MAIN_CODE, "Main", "STORE", timezone),
        (TRANSIT_CODE, "Internal transit", "INTERNAL_TRANSIT", None),
    ):
        assert_kind(kind, system=True)
        assert_code_available(code, system=True)
        builtins.append(
            await create(
                Warehouse,
                code=code,
                name=name,
                kind=kind,
                is_system=True,
                is_active=True,
                timezone=zone,
            )
        )
    main, transit = builtins
    return await create(
        CompanyWarehouseConfiguration,
        main_warehouse_id=main.id,
        transit_warehouse_id=transit.id,
        source_version=source_version,
        **dict.fromkeys(DEFAULT_POINTERS, main.id),
    )


async def policies(
    db: AsyncSession,
    company: uuid.UUID,
    config: CompanyWarehouseConfiguration,
    create: Creator,
    before_create: Callable[[], Awaitable[None]] | None = None,
) -> None:
    # Deferred because the public operation-policy commands provision locations.
    from catalog.tasks.warehouse_operations import (
        MAIN_FLAGS,
        TRANSIT_FLAGS,
        next_number,
        open_revision,
    )

    for warehouse, flags in (
        (config.main_warehouse_id, MAIN_FLAGS),
        (config.transit_warehouse_id, TRANSIT_FLAGS),
    ):
        if await open_revision(db, company, warehouse) is None:
            if before_create is not None:
                await before_create()
            await create(
                WarehouseOperationPolicyRevision,
                warehouse_id=warehouse,
                revision=await next_number(db, company, warehouse),
                effective_from=utcnow(),
                effective_to=None,
                **flags,
            )
