"""Native row locks serialize two independent first-run completion transactions."""

from __future__ import annotations

import asyncio
import time

import pytest
from billing_platform.db import create_engine, create_session_factory, unfiltered
from billing_platform.oidc import VerifiedClaims
from sqlalchemy import select

from identity.models import Outbox, PlatformInstallation, RoleAssignment, Tenant, User
from identity.schemas.setup import SetupRequest
from identity.seeds.installation import seed_installation
from identity.seeds.regional import seed_regional_defaults
from identity.seeds.roles import seed_system_roles
from identity.services.setup import provision
from tests.factories import build_country, build_currency
from tests.test_platform_setup import BODY


@pytest.mark.mysql
async def test_concurrent_completion_commits_one_administrator(mysql_url: str) -> None:
    engine = create_engine(mysql_url)
    factory = create_session_factory(engine)
    # mysql_url must be a disposable schema. Test its native locking, using full model DDL.
    from billing_platform.db import Base

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db, db.begin():
        db.add(build_currency())
        await db.flush()
        db.add(build_country())
        await db.flush()
        await seed_system_roles(db)
        await seed_installation(db)
        await seed_regional_defaults(db)
    now = int(time.time())
    claims = VerifiedClaims(
        iss="https://setup.test/",
        aud="setup",
        sub="mysql-setup-check",
        exp=now + 300,
        iat=now,
        auth_time=now,
        scope="billing.api",
        email="setup@example.invalid",
        email_verified=True,
    )

    async def complete():
        async with factory() as db, db.begin():
            return await provision(db, SetupRequest(**BODY), claims)

    try:
        left, right = await asyncio.gather(complete(), complete())
        assert left == right
        async with factory() as db:
            with unfiltered():
                assert len(list(await db.scalars(select(Tenant)))) == 1
                assert len(list(await db.scalars(select(User)))) == 1
                assert len(list(await db.scalars(select(RoleAssignment)))) == 1
                assert len(list(await db.scalars(select(Outbox)))) == 4
            assert (await db.scalar(select(PlatformInstallation))).completed_at is not None
    finally:
        await engine.dispose()
