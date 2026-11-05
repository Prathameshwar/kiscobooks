"""Explicit, audited metadata backfill for one existing company after schema upgrade."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import uuid

from billing_platform.company_context import CompanyContext
from billing_platform.db import create_engine, tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.master_metadata import (
    METADATA_VERSION,
    group_metadata,
    template_group_defaults,
)
from accounting.domain.rules import GroupNode, hierarchy
from accounting.models import masters as m
from accounting.resources import BY_NAME
from accounting.seeds.templates import GROUPS
from accounting.tasks.commands import audit, values_of


async def backfill_company(
    factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> int:
    """Trusted deployment operation: explicit scope, no hierarchy/identity rewriting."""
    with tenant_scope(tenant_id):
        async with factory() as db, db.begin():
            setup = await db.scalar(
                select(m.AccountingSetup)
                .where(m.AccountingSetup.company_id == company_id)
                .with_for_update()
            )
            if setup is None:
                raise ConflictError("company setup is unavailable")
            if setup.metadata_version == METADATA_VERSION:
                return 0
            if setup.metadata_version != 0:
                raise ConflictError("unsupported company metadata version")
            heads = {
                head.id: head.nature
                for head in await db.scalars(
                    select(m.AccountHead).where(m.AccountHead.company_id == company_id)
                )
            }
            groups = list(
                await db.scalars(
                    select(m.AccountGroup)
                    .where(m.AccountGroup.company_id == company_id)
                    .limit(10001)
                )
            )
            if len(groups) > 10000:
                raise ConflictError("hierarchy exceeds the supported group capacity")
            paths = hierarchy([GroupNode(row.id, row.parent_id, row.head_id) for row in groups])
            depths: dict[uuid.UUID, int] = {}
            for _, descendant, depth in paths:
                depths[descendant] = max(depths.get(descendant, 0), depth)
            by_id = {row.id: row for row in groups}
            order = {code: index for index, (code, _, _, _) in enumerate(GROUPS, 1)}
            current = Access(
                Actor(tenant_id=tenant_id, user_id=actor_id),
                CompanyContext(
                    issued_at=int(time.time()),
                    tenant_id=tenant_id,
                    company_id=company_id,
                    user_id=actor_id,
                    base_currency=setup.base_currency,
                ),
            )
            count = 0
            spec = BY_NAME["account_group"]
            for row in sorted(groups, key=lambda item: depths[item.id]):
                if row.head_id not in heads:
                    raise ConflictError("group head is unavailable")
                code = row.system_key.removeprefix("group.") if row.system_key else ""
                proposed = template_group_defaults(code, order.get(code, 0))
                parent = by_id.get(row.parent_id) if row.parent_id is not None else None
                if parent is not None and code != "STOCK":
                    proposed["affects_gross_profit"] = None
                proposed.update(
                    group_metadata(
                        proposed,
                        heads[row.head_id],
                        {"affects_gross_profit": parent.affects_gross_profit} if parent else None,
                        system_key=row.system_key,
                    )
                )
                before = values_of(row, spec)
                changed = {key for key, value in proposed.items() if before[key] != value}
                if changed:
                    for key, value in proposed.items():
                        setattr(row, key, value)
                    row.row_version += 1
                    row.updated_by = actor_id
                    await db.flush()
                    audit(db, current, spec, row, "update", changed)
                    count += 1
            setup.metadata_version = METADATA_VERSION
            setup.generation += 1
            setup.row_version += 1
            setup.updated_by = actor_id
            await db.flush()
            audit(
                db,
                current,
                BY_NAME["accounting_setup"],
                setup,
                "metadata_upgrade",
                {"metadata_version"},
            )
            return count


async def run(tenant_id: uuid.UUID, company_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    engine = create_engine(os.environ["ACCOUNTING_DATABASE_URL"])
    try:
        await backfill_company(
            async_sessionmaker(engine, expire_on_commit=False),
            tenant_id=tenant_id,
            company_id=company_id,
            actor_id=actor_id,
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-id", type=uuid.UUID, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.tenant_id, args.company_id, args.actor_id))


if __name__ == "__main__":
    main()
