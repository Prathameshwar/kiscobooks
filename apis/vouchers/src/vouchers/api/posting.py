"""Capability-gated money and invoice command producer."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandReceipt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response
from vouchers.models import core as m
from vouchers.schemas.configuration import Contract, Version
from vouchers.tasks import posting
from vouchers.tasks.access import authorize
from vouchers.tasks.common import command, get

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERRORS)


class PostingOperation(Contract):
    operation_id: uuid.UUID
    execution_id: uuid.UUID
    voucher_id: uuid.UUID
    status: str
    row_version: int


class ReverseRequest(Version):
    posting_date: dt.date
    reason: str = Field(min_length=3, max_length=500)


@router.post("/vouchers/{object_id}/reverse", response_model=PostingOperation, status_code=202)
async def reverse_voucher(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ReverseRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    authorize(current, "reverse")
    if not (
        request.app.state.settings.money_execution_enabled
        or request.app.state.settings.stock_execution_enabled
    ):
        raise ConflictError("voucher execution has not been activated")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await posting.reverse(
            db,
            current,
            object_id,
            body.expected_version,
            body.posting_date,
            body.reason,
            money_enabled=request.app.state.settings.money_execution_enabled,
            stock_enabled=request.app.state.settings.stock_execution_enabled,
        )
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, m.VoucherOperation, uuid.UUID(refs["id"]))
        return {
            "operation_id": str(row.id),
            "execution_id": str(row.execution_id),
            "voucher_id": str(row.voucher_id),
            "status": row.status,
            "row_version": row.row_version,
        }

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "reverse",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.post("/vouchers/{object_id}/post", response_model=PostingOperation, status_code=202)
async def post_voucher(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: Version,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    authorize(current, "post")
    if not (
        request.app.state.settings.money_execution_enabled
        or request.app.state.settings.invoice_execution_enabled
        or request.app.state.settings.stock_execution_enabled
    ):
        raise ConflictError("voucher execution has not been activated")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await posting.post(
            db,
            current,
            object_id,
            body.expected_version,
            money_enabled=request.app.state.settings.money_execution_enabled,
            invoice_enabled=request.app.state.settings.invoice_execution_enabled,
            stock_enabled=request.app.state.settings.stock_execution_enabled,
        )
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, m.VoucherOperation, uuid.UUID(refs["id"]))
        return {
            "operation_id": str(row.id),
            "execution_id": str(row.execution_id),
            "voucher_id": str(row.voucher_id),
            "status": row.status,
            "row_version": row.row_version,
        }

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "post",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )
