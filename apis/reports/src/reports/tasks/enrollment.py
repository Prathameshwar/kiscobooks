"""Resolve current collection scopes; configured exact scopes stay supported."""

import uuid

import httpx
from billing_platform.service_auth import CompanyServiceScope
from reporting_contract.enrollment import discover, scope_allowed
from reporting_contract.transport import Owner

from reports.config import Settings


async def owners(settings: Settings, client: httpx.AsyncClient) -> tuple[Owner, ...]:
    dynamic: tuple[CompanyServiceScope, ...] = ()
    if settings.enrollment_source and any(o.allow_enrolled_companies for o in settings.owners):
        dynamic = await discover(client, settings.enrollment_source)
    chosen: dict[tuple[uuid.UUID, uuid.UUID], Owner] = {}
    for owner in settings.owners:
        for scope in (*owner.scopes, *(dynamic if owner.allow_enrolled_companies else ())):
            chosen.setdefault(
                (scope.tenant_id, scope.company_id), owner.model_copy(update={"scopes": (scope,)})
            )
    return tuple(chosen.values())


async def owner_for(settings: Settings, tenant: uuid.UUID, company: uuid.UUID) -> Owner | None:
    for owner in settings.owners:
        if await scope_allowed(owner, settings.enrollment_source, tenant, company):
            return owner.model_copy(
                update={"scopes": (CompanyServiceScope(tenant_id=tenant, company_id=company),)}
            )
    return None


async def retained_scopes(settings: Settings) -> set[tuple[uuid.UUID, uuid.UUID]]:
    scopes = {(s.tenant_id, s.company_id) for a in settings.authority_sources for s in a.scopes}
    if settings.enrollment_source and any(
        a.allow_enrolled_companies for a in settings.authority_sources
    ):
        async with httpx.AsyncClient(trust_env=False) as client:
            scopes.update(
                (s.tenant_id, s.company_id)
                for s in await discover(client, settings.enrollment_source, retained=True)
            )
    return scopes
