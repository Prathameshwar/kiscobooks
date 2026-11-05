"""Read-only authoritative invoice preview after closing the document read transaction."""

import uuid
from decimal import Decimal
from typing import Any, NamedTuple

import httpx
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import CommandReceipt
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import InvoiceCalculationDetail, InvoicePolicy, InvoicePreviewCommand

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response
from vouchers.domain.invoice import (
    UNPOSTABLE_PURCHASE,
    carries_unpostable_purchase_scope,
    goods_bill,
)
from vouchers.models import core as m
from vouchers.schemas.configuration import Contract, Version
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.owners import Owner
from vouchers.schemas.reads import VoucherDetail
from vouchers.tasks import documents
from vouchers.tasks.access import authorize, denied
from vouchers.tasks.common import command, expected, get
from vouchers.tasks.configuration import effective
from vouchers.tasks.documents import content, revision_for, validate_masters
from vouchers.tasks.master_lookup import owner_for

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERRORS)


def require_readable_inputs(current: Access, payload: dict[str, Any]) -> None:
    if denied(
        current,
        "vouchers.voucher",
        {"invoice", "lines", "currency", "document_date", "posting_date"},
        "read",
        payload,
    ):
        raise PermissionDeniedError("invoice calculation inputs are not readable")
    for line in payload.get("lines", []):
        if denied(current, "vouchers.voucher_item", set(line["item"]), "read", line["item"]):
            raise PermissionDeniedError("invoice item inputs are not readable")


class InvoiceAcceptance(Contract):
    expected_version: int = Field(strict=True, ge=1)
    calculation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class Snapshot(NamedTuple):
    """One revision's owner request, read in a short transaction closed before any owner call."""

    revision_id: uuid.UUID
    command: InvoicePreviewCommand


async def snapshot(
    request: Request,
    current: Access,
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    expected_version: int,
    *,
    acceptance: bool = False,
) -> Snapshot | None:
    """The owner request for the current revision, or None when an acceptance is not current.

    An acceptance whose voucher is no longer a draft at the version asked about is a replay or a
    stale request. It is not previewed here: the command transaction replays the retained receipt
    or refuses it, so a replay never needs the owner.
    """
    if current.authority is None or current.context.finance is None:
        raise ConflictError("invoice preview requires current financial authority")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            voucher = await get(db, current, m.Voucher, object_id)
            if acceptance and (
                voucher.row_version != expected_version or voucher.status != "DRAFT"
            ):
                return None
            expected(voucher, expected_version)
            revision = await revision_for(db, current, voucher)
            payload = await content(db, current, revision)
            require_readable_inputs(current, payload)
            policy, evidence = await effective(
                db,
                current,
                revision.type_revision_id,
                date=revision.document_date,
                posting_date=revision.posting_date,
                class_id=revision.class_id,
            )
            parsed = VoucherInput.model_validate(payload)
            if (
                parsed.invoice is None
                or parsed.posting_date is None
                or evidence["digest"] != revision.configuration_hash
            ):
                raise ConflictError("current invoice revision and posting date are required")
            if acceptance and carries_unpostable_purchase_scope(
                parsed, kind=evidence["kind"], goods_allowed=True
            ):
                raise ValidationFailedError(UNPOSTABLE_PURCHASE)
            await validate_masters(db, current, parsed)
            command = InvoicePreviewCommand.model_validate(
                {
                    "tenant_id": current.actor.tenant_id,
                    "company_id": company_id,
                    "actor_user_id": current.actor.user_id,
                    "authority": current.authority,
                    "kind": evidence["kind"],
                    "profile": evidence["profile"],
                    "currency": parsed.currency,
                    "document_date": parsed.document_date,
                    "posting_date": parsed.posting_date,
                    "invoice": parsed.invoice,
                    "policy": policy.invoice or InvoicePolicy(),
                    "configuration_hash": revision.configuration_hash,
                    "company_configuration_hash": current.context.finance.configuration_hash,
                    # A goods bill sends its stock lines so Accounting reads each item's facts.
                    **(
                        {"stock": parsed.stock} if goods_bill(parsed, kind=evidence["kind"]) else {}
                    ),
                }
            )
            return Snapshot(revision.id, command)


def refusal(response: httpx.Response) -> str:
    """The owner's own reason when it gave one: the same words its API shows this user."""
    generic = "invoice calculation was refused; verify accounts, configuration and tax evidence"
    try:
        reason = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return generic
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
        return generic
    return "invoice calculation was refused: " + reason.strip()


async def calculate(owner: Owner, command: InvoicePreviewCommand) -> InvoiceCalculationDetail:
    """Ask the owner for the authoritative calculation; no transaction is held meanwhile."""
    from fastapi import HTTPException
    from voucher_execution.transport import ExecutionClient

    try:
        async with httpx.AsyncClient(timeout=15) as transport:
            client = ExecutionClient(
                transport, owner.origin, owner.key_id, owner.secret.get_secret_value().encode()
            )
            return await client.preview(command)
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 403:
            raise PermissionDeniedError(
                "invoice calculation inputs are not readable at the owner"
            ) from error
        if error.response.status_code in {409, 422}:
            raise ConflictError(refusal(error.response)) from error
        raise HTTPException(503, "invoice calculation owner is unavailable") from error
    except httpx.RequestError as error:
        raise HTTPException(503, "invoice calculation owner is unavailable") from error


async def verified_revision(
    request: Request,
    current: Access,
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: InvoiceAcceptance,
) -> tuple[uuid.UUID, Decimal] | tuple[None, None]:
    """The revision whose owner calculation equals the hash the client asks to accept.

    A saved acceptance is trusted by submission and approval, so it is only stored after the
    owner's own preview of this exact revision, taken now, produces the same hash. Accounting
    repeats the comparison at posting; this makes a stale or invented hash fail at the click.
    Returns ``(None, None)`` for a replay or stale request (see ``snapshot``).
    """
    pinned = await snapshot(
        request, current, company_id, object_id, body.expected_version, acceptance=True
    )
    if pinned is None:
        return None, None
    owner = owner_for(
        request.app.state.settings.execution_owner,
        current.actor.tenant_id,
        company_id,
        "invoice calculation",
    )
    calculation = await calculate(owner, pinned.command)
    if calculation.calculation_hash != body.calculation_hash:
        raise ConflictError(
            "the invoice calculation differs from the owner's current calculation; "
            "preview the revision again before accepting it"
        )
    return pinned.revision_id, calculation.payable


@router.post("/vouchers/{object_id}/invoice-acceptance", response_model=VoucherDetail)
async def accept_invoice(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: InvoiceAcceptance,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    authorize(current, "edit")
    authorize(current, "read")
    verified, payable_total = await verified_revision(request, current, company_id, object_id, body)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        voucher = await get(db, current, m.Voucher, object_id, lock=True)
        expected(voucher, body.expected_version)
        if voucher.status != "DRAFT":
            raise ConflictError("invoice calculation can only be accepted on a draft")
        revision = await revision_for(db, current, voucher)
        payload = await content(db, current, revision)
        invoice = payload.get("invoice")
        if not isinstance(invoice, dict):
            raise ConflictError("current revision has no invoice calculation")
        _, evidence = await effective(
            db,
            current,
            revision.type_revision_id,
            date=revision.document_date,
            posting_date=revision.posting_date,
            class_id=revision.class_id,
        )
        if (
            evidence["kind"] not in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"}
            or evidence["profile"] != "STANDARD"
            or evidence["digest"] != revision.configuration_hash
            or revision.posting_date is None
        ):
            raise ConflictError("invoice configuration changed or is unsupported")
        require_readable_inputs(current, payload)
        if carries_unpostable_purchase_scope(
            VoucherInput.model_validate(payload), kind=evidence["kind"], goods_allowed=True
        ):
            raise ValidationFailedError(UNPOSTABLE_PURCHASE)
        if verified != revision.id:
            # Fail closed: never store a hash the owner has not confirmed for this revision.
            raise ConflictError("the invoice calculation could not be verified; try again")
        payload["invoice"] = invoice | {"accepted_calculation_hash": body.calculation_hash}
        row = await documents.write(
            db,
            current,
            VoucherInput.model_validate(payload),
            voucher_id=object_id,
            version=body.expected_version,
            accepted_calculation_hash=body.calculation_hash,
            payable_total=payable_total,
        )
        await db.flush()
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await documents.detail(db, current, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "edit",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.post("/vouchers/{object_id}/invoice-preview", response_model=InvoiceCalculationDetail)
async def preview_invoice(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: Version,
    request: Request,
    response: Response,
    current: Access = Depends(access),
) -> InvoiceCalculationDetail:
    authorize(current, "read")
    response.headers["Cache-Control"] = "no-store"
    owner = owner_for(
        request.app.state.settings.execution_owner,
        current.actor.tenant_id,
        company_id,
        "invoice calculation",
    )
    pinned = await snapshot(request, current, company_id, object_id, body.expected_version)
    if pinned is None:  # unreachable: only an acceptance may skip a voucher that is not current
        raise ConflictError("current invoice revision and posting date are required")
    return await calculate(owner, pinned.command)
