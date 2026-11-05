"""Trusted owner adapter API: publish stock evidence in the stock owner's transaction.

No HTTP stock authoring or posting admission is provided here. Callers must supply stable
source UUIDs and lock the company's AccountingSetup before their operational stock changes.
The existing reporting-feed listeners fence and export only committed evidence.
"""

import uuid
from collections.abc import Iterable
from itertools import islice
from typing import Any

from billing_platform.errors import ConflictError
from reporting_contract.inventory import InventoryRecord
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models.inventory_reporting import InventoryReportRecord


async def publish(
    db: AsyncSession,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    records: Iterable[tuple[uuid.UUID, dict[str, Any]]],
) -> None:
    """Upsert a bounded page of stable owner identities; completeness is coverage evidence.

    All pages plus coverage must commit in one owner transaction. This function never commits,
    does not fabricate coverage, and is not callable as a public stock import.
    """
    from sqlalchemy import select

    from accounting.tasks.reporting_feed import lock

    page = list(islice(records, 201))
    if len(page) > 200 or len({identity for identity, _ in page}) != len(page):
        raise ConflictError("inventory evidence page exceeds its bound or repeats an identity")
    setup = await db.run_sync(lambda sync: lock(sync, company))
    if setup.tenant_id != tenant:
        raise ConflictError("inventory evidence tenant differs from company")
    payloads = {
        identity: InventoryRecord.model_validate(value).model_dump(mode="json")["payload"]
        for identity, value in page
    }
    existing = (
        {
            row.id: row
            for row in await db.scalars(
                select(InventoryReportRecord).where(
                    InventoryReportRecord.company_id == company,
                    InventoryReportRecord.id.in_(payloads),
                )
            )
        }
        if payloads
        else {}
    )
    for identity, payload in payloads.items():
        if identity in existing:
            row = existing[identity]
            if row.payload != payload:
                row.payload = payload
                row.row_version += 1
        else:
            db.add(
                InventoryReportRecord(
                    id=identity,
                    tenant_id=tenant,
                    company_id=company,
                    payload=payload,
                )
            )
