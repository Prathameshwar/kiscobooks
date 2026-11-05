"""Durable registration-review delivery. Run with --env-file private.env [--once]."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from billing_platform.authz import ScopePath
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.errors import PermissionDeniedError
from sqlalchemy import select

from identity.api.auth import Actor
from identity.api.security import lock_tenant
from identity.config import Settings
from identity.models import AccountReview, AccountReviewCommand, PlatformInstallation, Tenant, User
from identity.services.account_review import reconcile
from identity.services.audit import record
from identity.services.identity_provider import build_account_directory
from identity.services.login import live_grants
from identity.services.provider_transport import provider_client

LOG = logging.getLogger(__name__)


async def tick(settings: Settings) -> int:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        async with provider_client(settings) as http:
            provider = build_account_directory(settings, http, factory)
            async with factory() as db:
                installation = await db.scalar(
                    select(PlatformInstallation).where(PlatformInstallation.key == "platform")
                )
                if installation is None or installation.tenant_id is None:
                    return 0
                tenant_id = installation.tenant_id
            processed = 0
            with tenant_scope(tenant_id):
                async with factory() as db:
                    ids = list(
                        await db.scalars(
                            select(AccountReviewCommand.id)
                            .where(AccountReviewCommand.status == "queued")
                            .order_by(AccountReviewCommand.created_at, AccountReviewCommand.id)
                            .limit(20)
                        )
                    )
                for command_id in ids:
                    async with factory() as db, db.begin():
                        await lock_tenant(db, tenant_id)
                        command = await db.get(AccountReviewCommand, command_id)
                        if command is None or command.status != "queued":
                            continue
                        user = await db.get(User, command.actor_id)
                        tenant = await db.get(Tenant, tenant_id)
                        configured = user is not None and (
                            settings.platform_operators.get(user.authentik_sub or "") == user.id
                            or (
                                installation.administrator_id == user.id
                                and installation.administrator_subject == user.authentik_sub
                            )
                        )
                        current = Actor(tenant_id, command.actor_id)
                        if user is not None:
                            current.grants, current.group_ids = await live_grants(db, user.id)
                        try:
                            if (
                                not configured
                                or user is None
                                or user.status != "active"
                                or tenant is None
                                or tenant.status != "active"
                            ):
                                raise PermissionDeniedError("review authority was revoked")
                            current.require_scope("platform.account.read", target=ScopePath())
                            current.require_scope("platform.account.review", target=ScopePath())
                        except PermissionDeniedError:
                            command.status, command.error_code = "blocked", "authority_revoked"
                            row = await db.get(AccountReview, command.account_id)
                            if row is not None:
                                row.needs_attention = True
                                row.version += 1
                            record(
                                db,
                                current,
                                action="platform.account_decision_blocked",
                                entity="account_review",
                                entity_id=command.account_id,
                                changes={
                                    "command_id": str(command.id),
                                    "error_code": command.error_code,
                                },
                            )
                            continue
                        await reconcile(db, current, provider, command, settings)
                        processed += 1
            return processed
    finally:
        await engine.dispose()


async def run(settings: Settings, once: bool, stop_file: Path | None = None) -> None:
    while stop_file is None or not stop_file.exists():
        try:
            await tick(settings)
        except Exception:
            # No provider exception body, applicant profile, database URL or token in logs.
            LOG.error("Account review delivery unavailable; saved commands will be retried.")
            if once:
                raise SystemExit(1) from None
        if once:
            return
        if stop_file is None:
            await asyncio.sleep(15)
        else:
            for _ in range(30):
                if stop_file.exists():
                    return
                await asyncio.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    asyncio.run(run(Settings(_env_file=args.env_file), args.once, args.stop_file))  # type: ignore[call-arg]  # pydantic-settings runtime environment-file argument
