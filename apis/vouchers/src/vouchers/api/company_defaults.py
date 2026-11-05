"""Company-scoped fixed provisioning with current authority and safe command replay."""

import uuid
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandReceipt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, unique_query
from vouchers.domain.company_defaults import FEATURES
from vouchers.schemas.company_defaults import DefaultsCreate, DefaultsResult
from vouchers.tasks.access import authorize
from vouchers.tasks.common import command
from vouchers.tasks.company_defaults import ensure_defaults

router = APIRouter(
    prefix="/v1/companies/{company_id}", responses=ERRORS, dependencies=[Depends(unique_query)]
)


@router.post("/voucher-type-defaults/bootstrap", response_model=DefaultsResult)
async def bootstrap(
    company_id: uuid.UUID,
    body: DefaultsCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    authorize(current, "read")
    features = current.context.features & FEATURES
    if body.expected_features is not None and body.expected_features != features:
        raise ConflictError("company capabilities changed; refresh and retry voucher setup")
    if current.context.finance is None or not current.context.finance.company_active:
        raise ConflictError("voucher defaults require an active company")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        result = await ensure_defaults(db, company_id, features, reconcile=True)
        if result.status == "NEEDS_REVIEW":
            # A conflict must not become a successful idempotency receipt: after the
            # operator resolves it, the same setup key must be able to run again.
            raise ConflictError(
                "default voucher codes need review; preserve existing types and review "
                "Voucher types in Company settings before retrying"
            )
        return CommandReceipt(200, result.model_dump(mode="json"))

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return DefaultsResult.model_validate(refs).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "type.manage",
            idempotency_key,
            body,
            mutate,
            render,
        )
    )
