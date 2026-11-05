"""Public reference data for account registration; no account reads or writes."""

import uuid

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import User, UserInvitation
from identity.schemas.base import StrictModel
from identity.services.tenant_choices import RegistrationChoices, registration_choices

router = APIRouter(prefix="/v1/registration", route_class=StrictRoute, responses=ERROR_RESPONSES)


class InvitationAvailability(StrictModel):
    available: bool


@router.get("/options", response_model=RegistrationChoices)
async def options(request: Request, response: Response) -> RegistrationChoices:
    # Intentionally public: only active global country/state names and codes.
    # Registration needs these before an account exists. The admission middleware
    # rate-limits anonymous callers; tenant data and account lookups are excluded.
    response.headers["Cache-Control"] = "no-store"
    async with request.app.state.session_factory() as db:
        return await registration_choices(db, request.app.state.reference_cache)


@router.get("/invitation", response_model=InvitationAvailability)
async def invitation(
    request: Request,
    response: Response,
    tenant: uuid.UUID,
    invitation_id: uuid.UUID = Query(alias="invitation"),
    email: str = Query(min_length=3, max_length=320),
) -> InvitationAvailability:
    # Public intentionally: a random invitation ID plus its tenant and invited email
    # can only confirm availability. No tenant, user or invitation data is returned.
    response.headers["Cache-Control"] = "no-store"
    if "@" not in email or "." not in email.split("@")[-1]:
        return InvitationAvailability(available=False)
    with tenant_scope(tenant):
        async with request.app.state.session_factory() as db:
            found = await db.scalar(
                select(UserInvitation.id)
                .join(User, User.id == UserInvitation.user_id)
                .where(
                    UserInvitation.id == invitation_id,
                    UserInvitation.status == "pending",
                    UserInvitation.expires_at > utcnow(),
                    User.status == "invited",
                    User.email == email.casefold(),
                )
                .limit(1)
            )
            return InvitationAvailability(available=found is not None)
