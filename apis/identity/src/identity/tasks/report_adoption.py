"""Preview/apply report enrollment for one existing company under live admin grants."""

import argparse
import asyncio
import json
import uuid

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.errors import PermissionDeniedError

from identity.api.auth import Actor
from identity.api.company_setup import enroll_existing_reports
from identity.api.security import lock_tenant
from identity.config import Settings
from identity.models import Company, Tenant, User
from identity.services.login import live_grants


async def adopt(
    settings: Settings,
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    apply: bool = False,
) -> dict[str, object]:
    engine = create_engine(settings.database_url)
    try:
        with tenant_scope(tenant):
            async with create_session_factory(engine).begin() as db:
                await lock_tenant(db, tenant)
                principal, owner, business = (
                    await db.get(User, user),
                    await db.get(Tenant, tenant),
                    await db.get(Company, company),
                )
                if (
                    principal is None
                    or principal.status != "active"
                    or owner is None
                    or owner.status != "active"
                    or business is None
                    or business.status != "active"
                    or business.requires_step_up
                ):
                    raise PermissionDeniedError("interactive active company authority is required")
                grants, groups = await live_grants(db, user)
                actor = Actor(tenant, user, grants, group_ids=groups)
                result = await enroll_existing_reports(company, current=actor, db=db)
                if not apply:
                    await db.rollback()
                return {
                    "company_id": str(company),
                    "would_enroll": result.enrolled,
                    "applied": apply,
                }
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--tenant", type=uuid.UUID, required=True)
    parser.add_argument("--company", type=uuid.UUID, required=True)
    parser.add_argument("--actor", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.env_file:
        import dotenv

        dotenv.load_dotenv(args.env_file)
    print(  # noqa: T201 -- explicit CLI preview/result; contains identifiers only.
        json.dumps(
            asyncio.run(
                adopt(
                    Settings.model_validate({}),
                    args.tenant,
                    args.company,
                    args.actor,
                    apply=args.apply,
                )
            )
        )
    )
