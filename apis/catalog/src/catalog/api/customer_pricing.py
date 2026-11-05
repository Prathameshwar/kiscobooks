"""Customer-pricing effective read for a future voucher price-evidence adapter.

Read only in v1. Authoring routes for `price_level_assignment` and its scope
are v1.1 (see docs/catalog-v1-completion-plan.md §4 Phase 3, "deferred"). The
tables and the pure-domain resolver ship in v1 so seeded source facts can
already resolve. Accounting owns the live party commercial-type master.
"""

import datetime as dt
import uuid

from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.schemas.customer_pricing import CustomerPricingEffective
from catalog.tasks.customer_pricing import effective_customer_pricing

_ALLOWED_QUERY = frozenset({"party_id", "as_of"})

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 503)},
)


@router.get(
    "/customer-pricing/effective",
    response_model=CustomerPricingEffective,
    operation_id="get_catalog_customer_pricing_effective",
)
async def get_effective(
    company_id: uuid.UUID,
    request: Request,
    party_id: uuid.UUID = Query(...),
    as_of: dt.date = Query(...),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CustomerPricingEffective:
    """Return the resolved price level and its audit chain for one party+date.

    The chain names the winning precedence step for a "why this price?" explanation.
    """
    if set(request.query_params) - _ALLOWED_QUERY:
        raise ValidationFailedError("only party_id and as_of are accepted")
    return await effective_customer_pricing(db, current, company_id, party_id=party_id, as_of=as_of)
