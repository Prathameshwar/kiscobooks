"""Synchronize only shipped branding through the normal deployment seed boundary.

No DDL, provider operations, customer renames or bootstrap authority changes.
Completed installations receive an atomic system audit event when the legacy name changes.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.outbox import audit_payload, emit
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.branding import PRODUCT_NAME, PUBLISHER_NAME, is_legacy_product_name
from identity.models.platform_installation import PlatformInstallation


@dataclass(frozen=True, slots=True)
class BrandingSeedOutcome:
    updated: int = 0


async def seed_branding(db: AsyncSession) -> BrandingSeedOutcome:
    row = await db.scalar(
        select(PlatformInstallation).where(PlatformInstallation.key == "platform").with_for_update()
    )
    if row is None:
        raise ValueError("run the Identity installation workflow before syncing branding")
    missing_default = row.completed_at is None and not (row.name or "").strip()
    if not missing_default and not is_legacy_product_name(row.name):
        return BrandingSeedOutcome()
    if row.completed_at is not None:
        if row.tenant_id is None:
            raise ValueError(
                "completed installation is missing its tenant; repair its evidence first"
            )
        payload = audit_payload(
            action="platform.details_updated",
            entity_type="platform_installation",
            entity_id=row.id,
            actor_user_id=None,
            category="system",
            changes={"name": {"changed": True}},
            reason="Product branding deployment",
        )
        payload.update(actor_type="system", source_service="identity")
        with tenant_scope(row.tenant_id):
            emit(
                db,
                tenant_id=row.tenant_id,
                aggregate_type="platform_installation",
                aggregate_id=row.id,
                event_type="platform.details_updated",
                payload=payload,
            )
            row.name = PRODUCT_NAME
            await db.flush()
    else:
        row.name = PRODUCT_NAME
        await db.flush()
    return BrandingSeedOutcome(updated=1)


async def apply_branding_seed(url: str, *, dry_run: bool = False) -> BrandingSeedOutcome:
    engine = create_engine(url)
    try:
        async with create_session_factory(engine)() as db, db.begin():
            result = await seed_branding(db)
            if dry_run:
                await db.rollback()
            return result
    finally:
        await engine.dispose()


class _DatabaseSettings(BaseSettings):
    # Only resolve the database setting, so an offline seed needs no login-provider secrets.
    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str

    def __init__(self, *, env_file: Path | None = None) -> None:
        super().__init__(_env_file=env_file)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report and roll back all changes")
    parser.add_argument("--env-file", type=Path, help="private Identity environment file")
    args = parser.parse_args(argv)
    try:
        settings = _DatabaseSettings(env_file=args.env_file)
        result = asyncio.run(apply_branding_seed(settings.database_url, dry_run=args.dry_run))
    except Exception:
        print(  # noqa: T201
            "Branding synchronization failed; check the private database configuration "
            "and installation evidence."
        )
        return 1
    print(f"{PRODUCT_NAME} / {PUBLISHER_NAME}: platform_installation updated={result.updated}")  # noqa: T201
    if args.dry_run:
        print("dry run: rolled back")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
