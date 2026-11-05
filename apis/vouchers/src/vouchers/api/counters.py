"""Scoped counter administration and drawer-session commands."""

import uuid
from typing import Any

from billing_platform.idempotency import CommandReceipt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.models.counter import CheckoutCounter, CounterOperator, CounterOutlet
from vouchers.schemas.counters import (
    CashMovement,
    CounterCreate,
    CounterMasterDetail,
    CounterOperatorDetail,
    CounterSessionDetail,
    MasterStatusUpdate,
    OperatorCreate,
    OperatorStatusUpdate,
    OutletCreate,
    SessionClose,
    SessionOpen,
)
from vouchers.tasks import counters
from vouchers.tasks.access import authorize
from vouchers.tasks.common import command, get

router = APIRouter(
    prefix="/v1/companies/{company_id}", responses=ERRORS, dependencies=[Depends(unique_query)]
)


def master_detail(row: CounterOutlet | CheckoutCounter) -> CounterMasterDetail:
    return CounterMasterDetail(
        id=row.id,
        company_id=row.company_id,
        code=row.code,
        name=row.name,
        status=row.status,
        row_version=row.row_version,
        outlet_id=row.outlet_id if isinstance(row, CheckoutCounter) else None,
    )


def operator_detail(row: CounterOperator) -> CounterOperatorDetail:
    return CounterOperatorDetail(
        id=row.id,
        company_id=row.company_id,
        counter_id=row.counter_id,
        user_id=row.user_id,
        status=row.status,
        row_version=row.row_version,
    )


@router.post(
    "/checkout-counters/{counter_id}/operators",
    response_model=CounterOperatorDetail,
    status_code=201,
)
async def assign_operator(
    company_id: uuid.UUID,
    counter_id: uuid.UUID,
    body: OperatorCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await counters.operator_create(db, current, counter_id, body)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, CounterOperator, uuid.UUID(refs["id"]))
        return operator_detail(row).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=counter_id,
        )
    )


@router.put(
    "/checkout-counters/{counter_id}/operators/{user_id}/status",
    response_model=CounterOperatorDetail,
)
async def set_operator_status(
    company_id: uuid.UUID,
    counter_id: uuid.UUID,
    user_id: uuid.UUID,
    body: OperatorStatusUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await counters.operator_status(db, current, counter_id, user_id, body)
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, CounterOperator, uuid.UUID(refs["id"]))
        return operator_detail(row).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=counter_id,
            path_ids=(user_id,),
        )
    )


@router.post("/counter-outlets", response_model=CounterMasterDetail, status_code=201)
async def create_outlet(
    company_id: uuid.UUID,
    body: OutletCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await counters.outlet_create(db, current, body)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, CounterOutlet, uuid.UUID(refs["id"]))
        return master_detail(row).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            idempotency_key,
            body,
            mutate,
            render,
        )
    )


@router.post("/checkout-counters", response_model=CounterMasterDetail, status_code=201)
async def create_counter(
    company_id: uuid.UUID,
    body: CounterCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await counters.counter_create(db, current, body)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, CheckoutCounter, uuid.UUID(refs["id"]))
        return master_detail(row).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            idempotency_key,
            body,
            mutate,
            render,
        )
    )


@router.get("/counter-outlets/{outlet_id}", response_model=CounterMasterDetail)
async def outlet_detail(
    company_id: uuid.UUID,
    outlet_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> CounterMasterDetail:
    authorize(current, "read")
    return master_detail(await get(db, current, CounterOutlet, outlet_id))


@router.get("/checkout-counters/{counter_id}", response_model=CounterMasterDetail)
async def counter_detail(
    company_id: uuid.UUID,
    counter_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> CounterMasterDetail:
    authorize(current, "read")
    return master_detail(await get(db, current, CheckoutCounter, counter_id))


@router.put("/counter-outlets/{outlet_id}/status", response_model=CounterMasterDetail)
async def set_outlet_status(
    company_id: uuid.UUID,
    outlet_id: uuid.UUID,
    body: MasterStatusUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await counters.outlet_status(db, current, outlet_id, body)
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, CounterOutlet, uuid.UUID(refs["id"]))
        return master_detail(row).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=outlet_id,
        )
    )


@router.put("/checkout-counters/{counter_id}/status", response_model=CounterMasterDetail)
async def set_counter_status(
    company_id: uuid.UUID,
    counter_id: uuid.UUID,
    body: MasterStatusUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await counters.counter_status(db, current, counter_id, body)
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, CheckoutCounter, uuid.UUID(refs["id"]))
        return master_detail(row).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=counter_id,
        )
    )


@router.post("/counter-sessions", response_model=CounterSessionDetail, status_code=201)
async def open_session(
    company_id: uuid.UUID,
    body: SessionOpen,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await counters.session_open(db, current, body)
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return CounterSessionDetail.model_validate(
            await counters.session_detail(db, current, uuid.UUID(refs["id"]))
        ).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "counter.operate",
            idempotency_key,
            body,
            mutate,
            render,
        )
    )


@router.get("/counter-sessions/{session_id}", response_model=CounterSessionDetail)
async def session_detail(
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await counters.session_detail(db, current, session_id)


@router.post("/counter-sessions/{session_id}/cash-events", response_model=CounterSessionDetail)
async def record_cash_movement(
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    body: CashMovement,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        await counters.cash_movement(db, current, session_id, body)
        return CommandReceipt(200, {"id": str(session_id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return CounterSessionDetail.model_validate(
            await counters.session_detail(db, current, uuid.UUID(refs["id"]))
        ).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "counter.operate",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=session_id,
        )
    )


@router.post("/counter-sessions/{session_id}/close", response_model=CounterSessionDetail)
async def close_session(
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    body: SessionClose,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        await counters.session_close(db, current, session_id, body)
        return CommandReceipt(200, {"id": str(session_id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return CounterSessionDetail.model_validate(
            await counters.session_detail(db, current, uuid.UUID(refs["id"]))
        ).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "counter.close",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=session_id,
        )
    )
