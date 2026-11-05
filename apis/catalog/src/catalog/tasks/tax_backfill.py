"""Run with python -m catalog.tasks.tax_backfill; republishes current GST state per company.

Bootstraps Accounting's tax replica (docs/tax-accounting-plan.md Phase 5) for companies whose
tax definitions predate the publication events, and repairs a replica rebuilt from empty.
For each subscribed company it takes the company policy lock, reads the current generation
``G`` and stages one ``catalog.tax_*.changed`` event per classification, rule and rate at
``source_version = G``:

* withdrawn classifications and rates go out as ``WITHDRAW`` (see
  ``catalog.events.tax_publication``), inactive rules as ``WITHDRAW``, everything else as
  ``PUBLISH``;
* a row that already has a publication staged at ``G`` is skipped, so rerunning the command
  stages nothing new. Accounting also ignores an equal generation, so even a duplicate would
  have one effect.

It changes no Catalog state and bumps no generation, so it writes no audit event. Holding the
company lock for the run means no tax command interleaves with the snapshot.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.service_auth import CompanyServiceScope
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.tax_publication import TAX_PUBLICATION_EVENTS
from catalog.models import Outbox
from catalog.models.tax import TaxRule
from catalog.models.tax_governance import TaxHistoryAction
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.tax_publication import ORDER, stage

CHUNK = 500


class TaxBackfillSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False, min_length=1)
    source_subscriptions: tuple[CompanyServiceScope, ...] = Field(min_length=1, max_length=1000)


@dataclass
class BackfillResult:
    generation: int
    staged: dict[str, int] = field(default_factory=dict)
    skipped: int = 0


async def withdrawn(
    db: AsyncSession, company: uuid.UUID, ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    return set(
        await db.scalars(
            select(TaxHistoryAction.target_id).where(
                TaxHistoryAction.company_id == company,
                TaxHistoryAction.action == "WITHDRAW",
                TaxHistoryAction.target_id.in_(ids),
            )
        )
    )


async def already_staged(
    db: AsyncSession, tenant: uuid.UUID, ids: Sequence[uuid.UUID], generation: int
) -> set[uuid.UUID]:
    """Aggregates with a publication at ``generation`` already on the outbox."""
    staged: set[uuid.UUID] = set()
    for aggregate, payload in await db.execute(
        select(Outbox.aggregate_id, Outbox.payload).where(
            Outbox.tenant_id == tenant,
            Outbox.aggregate_id.in_(ids),
            Outbox.event_type.in_(TAX_PUBLICATION_EVENTS),
        )
    ):
        if isinstance(payload, dict) and payload.get("source_version") == generation:
            staged.add(aggregate)
    return staged


def action(value: Any, withdrawn_ids: set[uuid.UUID]) -> str:
    if isinstance(value, TaxRule):
        return "PUBLISH" if value.is_active else "WITHDRAW"
    return "WITHDRAW" if value.id in withdrawn_ids else "PUBLISH"


async def backfill_company(
    db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID, *, chunk: int = CHUNK
) -> BackfillResult:
    """Stage the company's current GST state at its current generation, once."""
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    result = BackfillResult(state.generation)
    for model in ORDER:
        after: uuid.UUID | None = None
        while True:
            stmt = select(model).where(model.company_id == company).order_by(model.id).limit(chunk)
            if after is not None:
                stmt = stmt.where(model.id > after)
            values: list[Any] = list(await db.scalars(stmt))
            if not values:
                break
            after = values[-1].id
            ids = [value.id for value in values]
            done = await already_staged(db, tenant, ids, state.generation)
            gone = set() if model is TaxRule else await withdrawn(db, company, ids)
            pending = [(value, action(value, gone)) for value in values if value.id not in done]
            result.skipped += len(values) - len(pending)
            count = await stage(db, state.generation, pending)
            key = str(model.__tablename__)
            result.staged[key] = result.staged.get(key, 0) + count
            await db.flush()
    return result


async def backfill(
    factory: async_sessionmaker[AsyncSession], scopes: Sequence[CompanyServiceScope]
) -> dict[tuple[uuid.UUID, uuid.UUID], BackfillResult]:
    """One transaction per company, each under that company's policy lock."""
    results: dict[tuple[uuid.UUID, uuid.UUID], BackfillResult] = {}
    for scope in scopes:
        with tenant_scope(scope.tenant_id):
            async with factory.begin() as db:
                results[scope.tenant_id, scope.company_id] = await backfill_company(
                    db, scope.tenant_id, scope.company_id
                )
    return results


async def run(settings: TaxBackfillSettings) -> dict[tuple[uuid.UUID, uuid.UUID], BackfillResult]:
    engine = create_engine(settings.database_url)
    try:
        return await backfill(
            create_session_factory(engine, guarded=True), settings.source_subscriptions
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args()
    try:
        settings = TaxBackfillSettings(_env_file=args.env_file)  # type: ignore[call-arg] # environment
        results = asyncio.run(run(settings))
    except Exception as exc:
        raise SystemExit("Catalog tax backfill failed: " + type(exc).__name__) from None
    for (tenant, company), result in results.items():
        staged = ", ".join(f"{key}={value}" for key, value in sorted(result.staged.items()))
        sys.stdout.write(
            f"tenant={tenant} company={company} generation={result.generation} "
            f"staged[{staged}] skipped={result.skipped}\n"
        )


if __name__ == "__main__":
    main()
