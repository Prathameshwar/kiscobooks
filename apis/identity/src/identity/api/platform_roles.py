"""Fresh configured operators reconcile fixed system roles through an audited API."""

from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, refresh_current
from identity.api.platform import fresh_platform_actor, platform_actor
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.schemas.platform_roles import RoleSeedCommand, RoleSeedPlan, RoleSeedResult
from identity.seeds.roles import seed_system_roles
from identity.services.audit import record
from identity.services.platform_details import installation
from identity.services.platform_roles import plan

router = APIRouter(
    prefix="/v1/platform/system-roles", route_class=StrictRoute, responses=ERROR_RESPONSES
)


async def authorize(
    db: AsyncSession, request: Request, current: Actor, *, write: bool = False
) -> None:
    await refresh_current(db, request, current)
    current.require_scope("platform.config.manage", target=ScopePath())
    await installation(db, lock=write)


@router.get("", response_model=RoleSeedPlan)
async def preview(request: Request, current: Actor = Depends(platform_actor)) -> RoleSeedPlan:
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            await authorize(db, request, current)
            return await plan(db)


@router.post("/reconcile", response_model=RoleSeedResult)
async def reconcile(
    body: RoleSeedCommand,
    request: Request,
    key: str = Header(alias="Idempotency-Key"),
    current: Actor = Depends(fresh_platform_actor),
) -> RoleSeedResult:
    async def check(db: AsyncSession, references: dict[str, Any] | None) -> None:
        await authorize(db, request, current, write=True)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        before = await plan(db, lock=True)
        if (
            before.current_digest != body.expected_current_digest
            or before.catalogue_digest != body.expected_catalogue_digest
        ):
            raise ConflictError("system roles changed; refresh and review the catalogue")
        role_outcome, grant_outcome = await seed_system_roles(db)
        after = await plan(db)
        changed = role_outcome.changed or grant_outcome.changed
        if changed:
            installed = await installation(db)
            record(
                db,
                current,
                action="platform.system_roles_reconciled",
                entity="platform_installation",
                entity_id=installed.id,
                reason=body.reason,
                changes={
                    "catalogue_digest": before.catalogue_digest,
                    "added_grants": grant_outcome.inserted,
                    "removed_grants": grant_outcome.revoked,
                },
            )
        value = RoleSeedResult(
            changed=changed,
            current_digest=after.current_digest,
            catalogue_digest=after.catalogue_digest,
            inserted_roles=role_outcome.inserted,
            updated_roles=role_outcome.updated,
            deactivated_roles=role_outcome.deactivated,
            added_grants=grant_outcome.inserted,
            removed_grants=grant_outcome.revoked,
        )
        return CommandReceipt(200, value.model_dump(mode="json"))

    async def render(db: AsyncSession, references: dict[str, Any]) -> RoleSeedResult:
        return RoleSeedResult.model_validate(references)

    with tenant_scope(current.tenant_id):
        result = await execute_idempotent(
            request.app.state.session_factory,
            CommandIdentity(
                current.tenant_id,
                None,
                current.user_id,
                "identity.platform.system_roles.reconcile",
                key,
                body.model_dump(mode="json"),
            ),
            authorize=check,
            mutate=mutate,
            render=render,
        )
    return result.value
