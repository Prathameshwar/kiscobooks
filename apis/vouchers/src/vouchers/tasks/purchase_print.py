"""Freeze masked saved input and authoritative amounts before durable PDF admission."""

import uuid
from typing import Any

import httpx
from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import CommandReceipt
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import InvoicePolicy, InvoicePreviewCommand
from voucher_execution.printing import PurchasePrintCommand
from voucher_execution.transport import ExecutionClient

from vouchers.api.auth import Access
from vouchers.api.invoices import require_readable_inputs
from vouchers.domain.invoice import carries_unpostable_purchase_scope, goods_bill
from vouchers.domain.purchase_print import assemble_snapshot, labels_unchanged, snapshot_hash
from vouchers.models import core as m
from vouchers.models.printing import VoucherPrintJob
from vouchers.schemas.configuration import Policy
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.printing import LayoutPreview, PrintCreate
from vouchers.schemas.reads import VoucherDetail
from vouchers.tasks.access import authorize, denied
from vouchers.tasks.common import audit, expected, get, values
from vouchers.tasks.documents import content, detail, revision_for
from vouchers.tasks.master_lookup import owner_for
from vouchers.tasks.print_authority import fingerprint
from vouchers.tasks.print_layout import resolve
from vouchers.tasks.stock_details import restricted as stock_restricted


async def prepare(
    request: Request,
    current: Access,
    identity: uuid.UUID,
    body: PrintCreate,
    *,
    pinned_layout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for action in ("read", "artifact.create", "artifact.read"):
        authorize(current, action)
    if body.layout_preview is not None:
        # A preview shows a design that may be unpublished: only someone who may read this
        # company's designs may see one, on top of reading and printing the bill.
        current.actor.require_scope(
            "design.template.read", target=ScopePath(company_id=current.context.company_id)
        )
    settings = request.app.state.settings
    if (
        settings.print_file_root is None
        or settings.print_broker_url is None
        or not any(
            scope.tenant_id == current.actor.tenant_id
            and scope.company_id == current.context.company_id
            for scope in settings.print_scopes
        )
    ):
        raise ConflictError("Purchase PDF printing is not configured for this company")
    if current.context.report_display is None or current.context.finance is None:
        raise ConflictError("refresh the session to load current company print formats")
    if current.authority is None:
        raise PermissionDeniedError("Purchase printing requires live user authority")
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            voucher = await get(db, current, m.Voucher, identity)
            expected(voucher, body.expected_version)
            revision = await revision_for(db, current, voucher)
            if revision.id != body.revision_id:
                raise ConflictError("the saved Purchase revision changed; reload before printing")
            payload = await content(db, current, revision)
            require_readable_inputs(current, payload)
            document = VoucherDetail.model_validate(await detail(db, current, identity))
            if document.kind != "PURCHASE" or document.profile != "STANDARD":
                raise ConflictError("this print service supports standard Purchase vouchers")
            if denied(
                current,
                "vouchers.voucher",
                {"status", "issue_number", "revision_number", "narration"},
                "read",
                payload,
            ):
                raise PermissionDeniedError("Purchase print header is not readable")
            parsed = VoucherInput.model_validate(payload)
            if parsed.invoice is None or parsed.posting_date is None:
                raise ConflictError("save an invoice and posting date before printing")
            if carries_unpostable_purchase_scope(parsed, kind="PURCHASE", goods_allowed=True):
                # The same boundary as acceptance: a product or mixed bill prints when every
                # goods line is the stock line it brings in (B24). Any other shape never
                # calculates, so there is nothing authoritative to print.
                raise ConflictError(
                    "this Purchase's goods lines do not match its stock lines; open the bill "
                    "to correct them before printing"
                )
            if parsed.currency != current.context.base_currency:
                # Accounting calculates and posts base-currency invoices only, so a foreign bill
                # has no authoritative amounts to print; say why instead of a generic failure.
                raise ConflictError(
                    "Purchase printing supports bills in the company's base currency only; this "
                    f"bill is in {parsed.currency}, the base currency is "
                    f"{current.context.base_currency}"
                )
            policy = Policy.model_validate(revision.configuration_evidence["policy"])
            command = InvoicePreviewCommand(
                tenant_id=current.actor.tenant_id,
                company_id=current.context.company_id,
                actor_user_id=current.actor.user_id,
                authority=current.authority,
                kind="PURCHASE",
                currency=parsed.currency,
                document_date=parsed.document_date,
                posting_date=parsed.posting_date,
                invoice=parsed.invoice,
                policy=policy.invoice or InvoicePolicy(),
                configuration_hash=revision.configuration_hash,
                company_configuration_hash=current.context.finance.configuration_hash,
                # A goods bill sends its stock lines so Accounting reads each item's facts.
                stock=parsed.stock if goods_bill(parsed, kind="PURCHASE") else None,
            )
            type_id = voucher.type_id
    owner = owner_for(
        settings.execution_owner,
        current.actor.tenant_id,
        current.context.company_id,
        "Purchase printing",
    )
    try:
        async with httpx.AsyncClient(timeout=15) as transport:
            client = ExecutionClient(
                transport, owner.origin, owner.key_id, owner.secret.get_secret_value().encode()
            )
            facts = await client.purchase_print(
                PurchasePrintCommand(
                    preview=command,
                    revision_id=body.revision_id,
                    require_posted=document.status in {"POSTED", "REVERSED"},
                )
            )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 403:
            raise PermissionDeniedError("Purchase print amounts are not readable") from error
        raise ConflictError(
            "Purchase print facts are unavailable; verify the saved invoice"
        ) from error
    except httpx.RequestError as error:
        raise ConflictError("Purchase print owner is unavailable; retry shortly") from error
    layout = pinned_layout or await resolve(
        settings.print_layout_owner,
        current.actor.tenant_id,
        current.context.company_id,
        type_id,
        parsed.currency,
        body.layout_preview,
    )
    if body.layout_preview is not None and (
        not layout.get("preview")
        or str(layout.get("version_id")) != str(body.layout_preview.version_id)
    ):
        raise ConflictError("the design version to preview was not the one resolved")
    if layout.get("preview") and layout.get("assets"):
        # A preview may show pictures placed only on an unpublished version, so it also needs
        # the right to read the company's design assets (checked again on every download).
        current.actor.require_scope(
            "design.asset.read", target=ScopePath(company_id=current.context.company_id)
        )
    saved = document.model_dump(mode="json", exclude_none=True)
    printable = {
        key: saved[key]
        for key in (
            "id",
            "company_id",
            "row_version",
            "revision_id",
            "revision_number",
            "status",
            "kind",
            "currency",
            "document_date",
            "posting_date",
            "issue_number",
            "narration",
        )
        if key in saved
    }
    return assemble_snapshot(
        document=printable,
        invoice=parsed.invoice,
        facts=facts,
        display=current.context.report_display.model_dump(mode="json"),
        layout=layout,
        stock=(
            parsed.stock
            if goods_bill(parsed, kind="PURCHASE") and not stock_restricted(current, payload)
            else None
        ),
    )


async def reauthorize(
    request: Request, current: Access, identity: uuid.UUID, snapshot: dict[str, Any]
) -> None:
    frozen = snapshot["layout"]
    latest = await prepare(
        request,
        current,
        identity,
        PrintCreate(
            expected_version=snapshot["document"]["row_version"],
            revision_id=snapshot["document"]["revision_id"],
            # A preview is delivered only while its reader may still read designs.
            layout_preview=LayoutPreview(
                template_id=frozen["template_id"], version_id=frozen["version_id"]
            )
            if frozen.get("preview")
            else None,
        ),
        pinned_layout=frozen,
    )
    if latest["calculation"]["calculation_hash"] != snapshot["calculation"]["calculation_hash"]:
        raise ConflictError("Purchase calculation changed; generate a fresh copy before printing")
    if latest["document"].get("stock_receipt") != snapshot["document"].get("stock_receipt"):
        raise ConflictError(
            "Purchase receiving details changed or are no longer readable; "
            "generate a fresh copy before printing"
        )
    # Names and the voucher number are read under the actor's rights at this moment. A value now
    # denied, or changed, must not be delivered from the old copy; the message carries no value.
    if not labels_unchanged(snapshot.get("labels") or {}, latest.get("labels") or {}):
        raise ConflictError(
            "Purchase print details changed or are no longer readable; generate a fresh copy "
            "before printing"
        )


async def admit(
    db: AsyncSession,
    current: Access,
    identity: uuid.UUID,
    body: PrintCreate,
    snapshot: dict[str, Any],
) -> CommandReceipt:
    voucher = await get(db, current, m.Voucher, identity, lock=True)
    expected(voucher, body.expected_version)
    revision = await revision_for(db, current, voucher)
    if revision.id != body.revision_id or voucher.status != snapshot["document"]["status"]:
        raise ConflictError("Purchase changed while print facts were being prepared")
    digest = snapshot_hash(snapshot)
    prior = await db.scalar(
        select(VoucherPrintJob)
        .where(
            VoucherPrintJob.company_id == current.context.company_id,
            VoucherPrintJob.request_hash == digest,
            VoucherPrintJob.permission_hash == fingerprint(current),
            VoucherPrintJob.status.in_(["PENDING", "RUNNING", "READY"]),
        )
        .order_by(VoucherPrintJob.id)
        .limit(1)
    )
    if prior is not None:
        return CommandReceipt(202, {"id": str(prior.id)})
    pending = await db.scalar(
        select(func.count(VoucherPrintJob.id)).where(
            VoucherPrintJob.company_id == current.context.company_id,
            VoucherPrintJob.status.in_(["PENDING", "RUNNING"]),
        )
    )
    if (pending or 0) >= 20:
        raise ConflictError("Purchase print queue is busy; retry after pending jobs finish")
    job = VoucherPrintJob(
        **values(current),
        voucher_id=identity,
        revision_id=body.revision_id,
        permission_hash=fingerprint(current),
        request_hash=digest,
        snapshot=snapshot,
        status="PENDING",
        attempt=0,
    )
    db.add(job)
    await db.flush()
    audit(db, current, "print_job", job.id, "create")
    from vouchers.tasks.print_worker import dispatch

    dispatch(db, job)
    return CommandReceipt(202, {"id": str(job.id)})
