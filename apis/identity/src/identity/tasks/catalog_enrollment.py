"""Audited operator backfill; existing disabled enrollments are never restored.

Run with --env-file and --apply after reviewing the default dry-run counts.
This command is an installation operation, not an HTTP route or user authority.
"""

from __future__ import annotations

import argparse
import asyncio

from billing_platform.db import create_engine, create_session_factory, unfiltered
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import Settings
from identity.models import CatalogSourceEnrollment, Company, Tenant


async def backfill(db: AsyncSession) -> int:
    count = 0
    after = None
    # Explicit operator-owned cross-tenant enrollment. Only active companies in
    # active tenants are eligible. Evidence and every insert share the transaction.
    with unfiltered():
        while True:
            statement = (
                select(Company)
                .join(Tenant, Company.tenant_id == Tenant.id)
                .where(
                    Company.status == "active",
                    Tenant.status == "active",
                    ~select(CatalogSourceEnrollment.id)
                    .where(
                        CatalogSourceEnrollment.tenant_id == Company.tenant_id,
                        CatalogSourceEnrollment.company_id == Company.id,
                    )
                    .exists(),
                )
            )
            if after is not None:
                statement = statement.where(Company.id > after)
            rows = list(await db.scalars(statement.order_by(Company.id).limit(200)))
            if not rows:
                return count
            for company in rows:
                row = CatalogSourceEnrollment(
                    id=uuid7(), tenant_id=company.tenant_id, company_id=company.id, is_active=True
                )
                db.add(row)
                emit(
                    db,
                    tenant_id=company.tenant_id,
                    aggregate_type="catalog_source_enrollment",
                    aggregate_id=row.id,
                    event_type="catalog_source.enrolled",
                    payload=audit_payload(
                        action="catalog_source.enrolled",
                        category="security",
                        entity_type="catalog_source_enrollment",
                        entity_id=row.id,
                        actor_user_id=None,
                        company_id=company.id,
                        reason="Operator enrollment of existing active company",
                        changes={"is_active": {"from": None, "to": True}},
                    ),
                )
                count += 1
            after = rows[-1].id
            await db.flush()


async def run(settings: Settings, *, apply: bool) -> int:
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as db:
            count = await backfill(db)
            if apply:
                await db.commit()
            else:
                await db.rollback()
            return count
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)  # type: ignore[call-arg] # private environment
    count = asyncio.run(run(settings, apply=args.apply))
    print(f"{'Enrolled' if args.apply else 'Would enroll'} {count} companies")  # noqa: T201
