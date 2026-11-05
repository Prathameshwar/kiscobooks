"""Fetch a small complete window before taking any source write lock."""

import uuid

import httpx
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from reporting_contract.contract import FactPage, Manifest
from reporting_contract.transport import Owner, request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.models.core import ReportGeneration
from reports.models.source_versions import ReportSourceEpoch
from reports.tasks.common import get
from reports.tasks.source_append import append_window


async def append_available(
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    owner: Owner,
    settings: Settings,
    tenant: uuid.UUID,
    company: uuid.UUID,
    generation_id: uuid.UUID,
    epoch_id: uuid.UUID,
    after: int,
    target: int,
) -> int:
    from reports.tasks.source_worker import capacity

    base = f"/internal/v1/reporting/{tenant}/{company}/changes"
    incoming: list[tuple[Manifest, FactPage]] = []
    count, size = 0, 0
    for sequence in range(after + 1, min(target, after + 32) + 1):
        proof = Manifest.model_validate(await request(client, owner, "GET", f"{base}/{sequence}"))
        capacity(proof, settings)
        if proof.kind != "CHANGE" or proof.sequence != sequence:
            raise ConflictError("source change identity differs")
        if count + proof.fact_count > 200:
            break
        page = FactPage.model_validate(
            await request(
                client, owner, "GET", f"{base}/{proof.id}/facts", {"after": "0", "limit": "200"}
            )
        )
        if page.next_after is not None or len(page.items) != proof.fact_count:
            break
        count += len(page.items)
        size += len(canonical_json(page.model_dump(mode="json")))
        if size > 2 * 1024 * 1024:
            break
        incoming.append((proof, page))
    if not incoming:
        return 0
    async with factory() as db, db.begin():
        generation = await get(db, company, ReportGeneration, generation_id, lock=True)
        epoch = await get(db, company, ReportSourceEpoch, epoch_id, lock=True)
        if generation.applied_sequence != after:
            return 0  # Another fenced/replayed invocation advanced; caller reloads the checkpoint.
        return len(incoming) if await append_window(db, generation, epoch, incoming) else 0
