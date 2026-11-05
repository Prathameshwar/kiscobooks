"""Short-lived company authentication proofs; Identity stores no password or session here."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Protocol

from billing_platform.db.platform_models import Outbox
from billing_platform.errors import PermissionDeniedError, PlatformError
from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import (
    Company,
    CustomFieldDefinition,
    Department,
    FieldPolicy,
    Membership,
    RoleAssignment,
)


class StepUpUnavailableError(PlatformError):
    code = "step_up_unavailable"
    status_code = 503


class StepUpRequiredError(PermissionDeniedError):
    code = "step_up_required"


class ProofStore(Protocol):
    async def put(self, key: str, value: str, seconds: int) -> None: ...
    async def get(self, key: str) -> str | None: ...
    async def take(self, key: str) -> str | None: ...


class RedisProofStore:
    def __init__(self, client_or_url: Redis | str) -> None:
        # Accept a ready client (the app shares one Redis client across the proof store
        # and the permission cache) or a URL (tests, and any caller that wants its own).
        # Either way the client is built by the shared platform factory.
        if isinstance(client_or_url, str):
            from billing_platform.cache import create_redis_client

            self.client: Redis = create_redis_client(client_or_url)
        else:
            self.client = client_or_url

    async def put(self, key: str, value: str, seconds: int) -> None:
        try:
            await self.client.set(key, value, ex=seconds)
        except RedisError as exc:
            raise StepUpUnavailableError("step-up verification is unavailable") from exc

    async def get(self, key: str) -> str | None:
        try:
            result = await self.client.get(key)
            return result if isinstance(result, str) else None
        except RedisError as exc:
            raise StepUpUnavailableError("step-up verification is unavailable") from exc

    async def take(self, key: str) -> str | None:
        try:
            result = await self.client.getdel(key)
            return result if isinstance(result, str) else None
        except RedisError as exc:
            raise StepUpUnavailableError("step-up verification is unavailable") from exc

    async def close(self) -> None:
        await self.client.aclose()


def store(request: Request) -> ProofStore:
    value: ProofStore | None = getattr(request.app.state, "proof_store", None)
    if value is None:
        raise StepUpUnavailableError("step-up verification is not configured")
    return value


def proof_key(current: Actor, company_id: uuid.UUID, proof: str) -> str:
    digest = hashlib.sha256(proof.encode()).hexdigest()
    return f"identity:step-up:proof:{current.tenant_id}:{current.user_id}:{company_id}:{digest}"


async def require_company(
    db: AsyncSession, request: Request, current: Actor, company_id: uuid.UUID
) -> None:
    requires_step_up = await db.scalar(
        select(Company.requires_step_up).where(Company.id == company_id)
    )
    if not requires_step_up:
        return
    claims = getattr(request.state, "verified_claims", None)
    proof = request.headers.get("x-company-step-up", "")
    if claims is None or not 20 <= len(proof) <= 128:
        raise StepUpRequiredError("fresh company authentication is required")
    encoded = await store(request).get(proof_key(current, company_id, proof))
    try:
        value: Any = json.loads(encoded or "null")
        if (
            not isinstance(value, dict)
            or value["subject"] != claims.sub
            or value["expires_at"] <= time.time()
        ):
            raise ValueError("expired proof")
        receipt = await db.scalar(
            select(Outbox.message_id).where(
                Outbox.message_id == uuid.UUID(value["receipt_id"]),
                Outbox.event_type == "company.step_up_completed",
            )
        )
        if receipt is None:
            raise ValueError("proof was not committed")
        from identity.models import User

        user = await db.get(User, current.user_id)
        if user is None or (
            user.tokens_valid_after_at
            and value["issued_at"] <= user.tokens_valid_after_at.timestamp()
        ):
            raise ValueError("revoked proof")
    except (ValueError, TypeError, KeyError) as exc:
        raise StepUpRequiredError("company authentication has expired") from exc


async def enforce_request(db: AsyncSession, request: Request, current: Actor) -> None:
    if request.url.path.endswith(("/step-up/challenge", "/step-up/complete")):
        return
    companies: set[uuid.UUID] = set()

    def add(value: object) -> None:
        if value is not None:
            resolved = uuid.UUID(str(value))
            if resolved.int:
                companies.add(resolved)

    async def add_scope(scope_type: object, scope_id: object) -> None:
        if scope_type == "company":
            add(scope_id)
        elif scope_type == "department" and scope_id is not None:
            department = await db.get(Department, uuid.UUID(str(scope_id)))
            if department:
                add(department.company_id)

    try:
        add(request.path_params.get("company_id"))
        add(request.query_params.get("company_id"))
        # FastAPI has already parsed JSON for typed bodies; the cached body is reused.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                body = await request.json()
            except (ValueError, UnicodeError):
                body = None
            if isinstance(body, dict):
                add(body.get("company_id"))
                await add_scope(body.get("scope_type"), body.get("scope_id"))
        membership_id = request.path_params.get("membership_id")
        if membership_id:
            membership = await db.get(Membership, uuid.UUID(str(membership_id)))
            if membership:
                add(membership.company_id)
        definition_id = request.path_params.get("definition_id")
        if definition_id:
            definition = await db.get(CustomFieldDefinition, uuid.UUID(str(definition_id)))
            if definition:
                add(definition.company_id)
        assignment_id = request.path_params.get("assignment_id")
        if assignment_id:
            assignment = await db.get(RoleAssignment, uuid.UUID(str(assignment_id)))
            if assignment:
                await add_scope(assignment.scope_type, assignment.scope_id)
        policy_id = request.path_params.get("policy_id")
        if policy_id:
            policy = await db.get(FieldPolicy, uuid.UUID(str(policy_id)))
            if policy:
                await add_scope(policy.scope_type, policy.scope_id)
    except (ValueError, TypeError) as exc:
        from billing_platform.errors import ValidationFailedError

        raise ValidationFailedError("invalid company scope identifier") from exc
    for company_id in sorted(companies):
        await require_company(db, request, current, company_id)
