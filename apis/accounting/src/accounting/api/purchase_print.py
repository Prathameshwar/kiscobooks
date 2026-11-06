"""Service signature and original user authority are both mandatory for print reads."""

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from fastapi import APIRouter, Request, Response
from voucher_execution.printing import PurchasePrintCommand

from accounting.api.auth import delegated_access
from accounting.api.voucher_execution import authorize, response
from accounting.tasks import invoice_goods
from accounting.tasks.purchase_print import facts
from accounting.tasks.stock_source_client import StockSourceUnavailableError

router = APIRouter()


@router.post("/internal/v1/purchase-print-facts", include_in_schema=False)
async def purchase_print_facts(body: PurchasePrintCommand, request: Request) -> Response:
    # Internal service authentication replaces an endpoint grant, but never the
    # delegated user's company, account and immutable financial-field permissions.
    command = body.preview
    operation = "voucher.purchase.print"
    credential, key_id, framed = await authorize(
        request, command.tenant_id, command.company_id, operation, await request.body()
    )
    current = delegated_access(
        command.authority,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        tenant_id=command.tenant_id,
        company_id=command.company_id,
        actor_user_id=command.actor_user_id,
    )
    # A goods bill's item facts (and the unit labels a print shows) come from Catalog before any
    # Accounting session opens, as for calculation. A posted bill's amounts are already frozen,
    # so a product changed or withdrawn since only costs that bill its unit labels.
    try:
        goods = await invoice_goods.acquire(request.app.state.settings, command, labels=True)
    except (
        ConflictError,
        PermissionDeniedError,
        StockSourceUnavailableError,
        ValidationFailedError,
    ):
        if not body.require_posted:
            raise
        goods = None
    with tenant_scope(command.tenant_id):
        async with request.app.state.session_factory() as db:
            result = await facts(db, current, body, goods)
    return response(
        credential,
        key_id,
        framed,
        operation,
        canonical_json(result.model_dump(mode="json"), maximum_bytes=1_048_576),
    )
