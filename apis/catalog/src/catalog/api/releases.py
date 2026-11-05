"""Publishing and reading a company's numbered stock-location policy releases.

docs/catalog-warehouses.md §5. Three routes, and the shape of each is a decision:

* ``POST`` answers 201 because a release *is* a new resource — the numbered, immutable record of
  a reviewed delivery. It costs ``warehouse.publish`` on top of ``warehouse.manage``: the flags
  were already reviewed one location at a time, and what this adds is the statement that the
  whole set is what consumers should now enforce.
* the collection ``GET`` answers a view rather than a cursor page. A company has one ordered
  series of releases, bounded in the projection, and the one thing every reader needs is the
  release *in force* — a page could be walked without it (docs/api-conventions.md).
* the item ``GET`` exists so an older release's acknowledgements stay readable. What a consumer
  enforced last week is the question an investigation actually asks.

There is no route that writes an acknowledgement. A client asserting "Billing applied this"
would make ``APPLIED`` mean nothing, so those rows arrive only from a signed source event.
"""

import uuid

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_receipt, no_query
from catalog.models.releases import CatalogPolicyRelease
from catalog.schemas.pricing import CommandOutput
from catalog.schemas.releases import PolicyReleaseInput, ReleaseDetail, ReleaseView
from catalog.tasks import releases as tasks
from catalog.tasks.pricing_commands import command
from catalog.tasks.warehouse_operations import WarehouseWork

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/policy-releases",
    response_model=ReleaseView,
    response_model_exclude_unset=True,
    operation_id="get_catalog_policy_releases",
)
async def get_releases(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ReleaseView:
    """Answers for a company that has never published: no release in force is a real answer."""
    no_query(request)
    return await tasks.release_view(db, current, company_id)


@router.post(
    "/policy-releases",
    response_model=CommandOutput,
    status_code=201,
    operation_id="publish_catalog_policy_release",
)
async def publish_release(
    company_id: uuid.UUID,
    body: PolicyReleaseInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    """Publish the company's stock-location policy as one numbered, dated release.

    The manifest is Catalog's, not the caller's: the body carries the date, the reason and the
    expectations the reviewer previewed, and nothing that could narrow what the release covers.
    """
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        CatalogPolicyRelease,
        body,
        idempotency_key,
        tasks.publish,
        action="publish",
        models=tasks.RELEASE_MODELS,
        work_type=WarehouseWork,
        publish_permission="warehouse.publish",
    )
    return command_receipt(result)


@router.get(
    "/policy-releases/{object_id}",
    response_model=ReleaseDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_policy_release",
)
async def get_release(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ReleaseDetail:
    no_query(request)
    return await tasks.release_detail(db, current, company_id, object_id)
