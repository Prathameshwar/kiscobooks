"""Fresh provider authentication is bound to a one-use company challenge."""

from __future__ import annotations

import json
import secrets
import time
import uuid

from billing_platform.authz import ScopePath
from billing_platform.errors import NotFoundError, PermissionDeniedError
from billing_platform.ids import uuid7
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import Company
from identity.schemas.base import StrictModel
from identity.services.audit import record
from identity.services.step_up import proof_key, store

router = APIRouter(
    prefix="/v1/companies/{company_id}/step-up", route_class=StrictRoute, responses=ERROR_RESPONSES
)


class Challenge(StrictModel):
    challenge_id: uuid.UUID
    expires_in_seconds: int
    auth_url: str


class Complete(StrictModel):
    challenge_id: uuid.UUID


class Proof(StrictModel):
    proof: str
    expires_in_seconds: int


@router.post("/challenge", response_model=Challenge)
async def challenge(
    company_id: uuid.UUID,
    request: Request,
    response: Response,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Challenge:
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    if await db.get(Company, company_id) is None:
        raise NotFoundError("company not found")
    claims = getattr(request.state, "verified_claims", None)
    if claims is None or not request.app.state.settings.public_auth_url:
        raise PermissionDeniedError("interactive provider authentication is required")
    challenge_id = uuid7()
    key = (
        f"identity:step-up:challenge:{current.tenant_id}:{current.user_id}:"
        f"{company_id}:{challenge_id}"
    )
    await store(request).put(
        key, json.dumps({"subject": claims.sub, "created_at": int(time.time())}), 300
    )
    record(
        db,
        current,
        action="company.step_up_challenged",
        entity="company",
        entity_id=company_id,
        company_id=company_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return Challenge(
        challenge_id=challenge_id,
        expires_in_seconds=300,
        auth_url=request.app.state.settings.public_auth_url.rstrip("/")
        + f"/step-up?company={company_id}&challenge={challenge_id}",
    )


@router.post("/complete", response_model=Proof)
async def complete(
    company_id: uuid.UUID,
    body: Complete,
    request: Request,
    response: Response,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Proof:
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    if await db.get(Company, company_id) is None:
        raise NotFoundError("company not found")
    key = (
        f"identity:step-up:challenge:{current.tenant_id}:{current.user_id}:"
        f"{company_id}:{body.challenge_id}"
    )
    claims = getattr(request.state, "verified_claims", None)
    encoded = await store(request).get(key)
    try:
        value = json.loads(encoded or "null")
        if (
            claims is None
            or claims.auth_time is None
            or not isinstance(value, dict)
            or value["subject"] != claims.sub
            or claims.auth_time <= value["created_at"]
            or not 0 <= time.time() - claims.auth_time <= 300
        ):
            raise ValueError("fresh provider login required")
    except (ValueError, KeyError, TypeError) as exc:
        raise PermissionDeniedError("challenge requires a new provider authentication") from exc
    # Atomic consumption prevents parallel completion from issuing multiple valid proofs.
    if await store(request).take(key) != encoded:
        raise PermissionDeniedError("challenge is expired or already used")
    proof = secrets.token_urlsafe(32)
    now = time.time()
    receipt = record(
        db,
        current,
        action="company.step_up_completed",
        entity="company",
        entity_id=company_id,
        company_id=company_id,
    )
    await store(request).put(
        proof_key(current, company_id, proof),
        json.dumps(
            {
                "subject": claims.sub,
                "issued_at": now,
                "expires_at": now + 300,
                "receipt_id": str(receipt.message_id),
            }
        ),
        300,
    )
    response.headers["Cache-Control"] = "no-store"
    return Proof(proof=proof, expires_in_seconds=300)
