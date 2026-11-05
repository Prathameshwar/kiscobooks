"""Authoritative read-only opening arithmetic with signed unit conversion facts."""

import datetime as dt
import hashlib

from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.stock_facts import StockFenceRequest

from accounting.api.auth import Access
from accounting.domain.opening_errors import OpeningConflictError as ConflictError
from accounting.domain.stock_opening import calculate
from accounting.schemas.stock_opening import OpeningCalculate, OpeningCalculated
from accounting.stock_resources import STOCK_MOVEMENT, STOCK_POSITION
from accounting.tasks.access import authorize
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.stock_effects import permitted
from accounting.tasks.stock_opening_control import require_capture_read
from accounting.tasks.stock_reads import view
from accounting.tasks.stock_source_client import StockSourceClient


async def preview(
    current: Access, body: OpeningCalculate, proof: DelegatedAuthority, source: StockSourceClient
) -> OpeningCalculated:
    require_capture_read(current)
    authorize(current, STOCK_POSITION, "read")
    if (
        not {"quantity", "value", "currency", "item_id", "warehouse_id"}
        <= view(current, STOCK_MOVEMENT)[2]
    ):
        raise PermissionDeniedError("opening valuation inputs and outputs must be readable")
    finance = financial_context(current)
    if body.stock_date != finance.books_begin_date:
        raise ConflictError("OPENING_DATE_MISMATCH: use the company's books begin date")
    facts = await source.acquire(
        StockFenceRequest(
            purpose="PREVIEW",
            tenant_id=current.actor.tenant_id,
            company_id=current.context.company_id,
            execution_id=uuid7(),
            actor_user_id=current.actor.user_id,
            authority=proof,
            authority_expires_at=utcnow() + dt.timedelta(seconds=45),
            stock_date=body.stock_date,
            content_hash=hashlib.sha256(canonical_json(body.model_dump(mode="json"))).hexdigest(),
            item_ids=(body.item_id,),
            warehouse_ids=(body.warehouse_id,),
            opening_unit_revision_ids=(body.opening.unit_revision_id,),
        )
    )
    item = next(row for row in facts.items if row.item_id == body.item_id)
    location = next(row for row in facts.warehouses if row.warehouse_id == body.warehouse_id)
    permitted(item, location, "OPENING_STOCK")
    if item.status != "ACTIVE" or item.family_status != "ACTIVE":
        raise ConflictError("PRODUCT_NOT_ACTIVE: activate this stock product first")
    if item.valuation_method not in {"FIFO", "MOVING_AVERAGE"}:
        raise ValidationFailedError(
            "opening stock currently supports FIFO or moving-average costing",
            fields={"item_id": "Select a product with a supported published valuation method."},
        )
    unit = next(
        (
            row
            for row in item.opening_units
            if row.revision_id == body.opening.unit_revision_id
            and row.unit_id == body.opening.entered_unit_id
            and row.item_id == body.item_id
        ),
        None,
    )
    if unit is None:
        raise ConflictError("UNIT_CONVERSION_INVALID: select the product's effective unit revision")
    if body.opening.received_on and body.opening.received_on > body.stock_date:
        raise ConflictError("opening receipt history cannot follow the cutover date")
    result = calculate(
        entered_quantity=body.opening.entered_quantity,
        numerator=unit.numerator,
        denominator=unit.denominator,
        conversion_mode=unit.conversion_mode,
        measured_base_quantity=body.opening.measured_base_quantity,
        entered_increment=unit.quantity_increment,
        base_increment=item.quantity_increment,
        entered_places=unit.quantity_decimal_places,
        base_places=item.quantity_decimal_places,
        serialized=item.serial_tracking,
        cost_mode=body.opening.cost_mode,
        unit_cost=body.opening.unit_cost,
        priced_quantity=body.opening.priced_quantity,
        received_value=body.received_value,
        places=finance.amount_precision,
        rounding=finance.rounding_mode,
    )
    return OpeningCalculated(
        company_id=current.context.company_id,
        currency=current.context.base_currency,
        base_quantity=result.base_quantity,
        received_value=result.value,
        derived_unit_cost=format(result.derived_unit_cost, ".4f"),
        derived_base_unit_cost=format(result.derived_base_unit_cost, ".4f"),
        unit_revision_id=unit.revision_id,
        catalog_generation=facts.policy_generation,
        source_version=facts.source_version,
    )
