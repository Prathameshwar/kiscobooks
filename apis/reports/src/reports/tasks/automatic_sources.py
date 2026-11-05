"""Coalesced automatic admission and owner-sequence freshness checks."""

import datetime as dt
import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from reporting_contract.contract import HeadBarrier
from reporting_contract.transport import Owner, request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.models.core import ReportGeneration
from reports.models.readiness import ReportReadiness
from reports.models.source_versions import (
    ReportGenerationRequest,
    ReportSourceCut,
    ReportSourceEpoch,
)
from reports.tasks.common import audit, company_lock


async def reconcile(
    factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    owner: Owner,
    tenant: uuid.UUID,
    company: uuid.UUID,
) -> None:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await company_lock(db, tenant, company)
            health = await db.scalar(
                select(ReportReadiness).where(ReportReadiness.company_id == company)
            )
            now = utcnow()
            if health is not None and health.next_attempt_at > now:
                return
            if health is None:
                health = ReportReadiness(tenant_id=tenant, company_id=company, next_attempt_at=now)
                db.add(health)
            # Reserve a bounded poll window before network work; a dead worker cannot
            # prevent later reconciliation. No owner call holds this transaction.
            health.next_attempt_at = now + dt.timedelta(seconds=10)
        try:
            base = f"/internal/v1/reporting/{tenant}/{company}"
            # Certify current Catalog definitions and stock positions before asking
            # for the financial head. The owner coalesces unchanged stock evidence.
            await request(client, owner, "POST", base + "/refresh-stock")
            head = HeadBarrier.model_validate(await request(client, owner, "GET", base + "/head"))
            if head.manifest is None or head.manifest.control.coverage_start is None:
                return  # Books initialization has not yet published its owner facts.
            if (head.manifest.tenant_id, head.manifest.company_id) != (
                tenant,
                company,
            ) or head.manifest.sequence != head.sequence:
                raise ValueError("owner barrier scope or sequence differs")
        except Exception as exc:
            failure = (
                "OWNER_ACCESS_DENIED"
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {401, 403}
                else "OWNER_UNAVAILABLE"
                if isinstance(exc, httpx.HTTPError | TimeoutError)
                else "OWNER_VERIFICATION_FAILED"
            )
            async with factory.begin() as db:
                await company_lock(db, tenant, company)
                health = await db.scalar(
                    select(ReportReadiness).where(ReportReadiness.company_id == company)
                )
                assert health is not None
                health.failure_code = failure
            return
        async with factory.begin() as db:
            await company_lock(db, tenant, company)
            health = await db.scalar(
                select(ReportReadiness).where(ReportReadiness.company_id == company)
            )
            assert health is not None
            health.owner_sequence, health.checked_at, health.failure_code = (
                head.sequence,
                utcnow(),
                None,
            )
            pending = await db.scalar(
                select(ReportGeneration.id)
                .where(
                    ReportGeneration.company_id == company,
                    ReportGeneration.status.in_(("PENDING", "BUILDING")),
                )
                .limit(1)
            )
            if pending:
                return
            latest = await db.scalar(
                select(ReportGeneration)
                .where(ReportGeneration.company_id == company)
                .order_by(ReportGeneration.id.desc())
                .limit(1)
            )
            if latest is not None and latest.status == "QUARANTINED":
                health.failure_code = "SOURCE_REVIEW_REQUIRED"
                return  # Integrity failures need review, never endless fresh rebuilds.
            cut = await db.scalar(
                select(ReportSourceCut)
                .join(ReportGeneration, ReportGeneration.id == ReportSourceCut.generation_id)
                .where(
                    ReportSourceCut.company_id == company,
                    ReportSourceCut.verification.is_not(None),
                    ReportGeneration.status == "READY",
                )
                .order_by(ReportSourceCut.id.desc())
                .limit(1)
            )
            if cut is not None and cut.sequence == head.sequence:
                return
            if cut is not None and cut.sequence > head.sequence:
                health.failure_code = "OWNER_SEQUENCE_REGRESSED"
                return
            parent = None
            if cut is not None:
                epoch = await db.get(ReportSourceEpoch, cut.epoch_id)
                if (
                    epoch is not None
                    and epoch.status == "READY"
                    and epoch.head_sequence == cut.sequence
                ):
                    parent = cut.id
            generation = ReportGeneration(tenant_id=tenant, company_id=company, snapshot_id=uuid7())
            db.add(generation)
            await db.flush()
            db.add(
                ReportGenerationRequest(
                    tenant_id=tenant,
                    company_id=company,
                    generation_id=generation.id,
                    strategy="REFRESH" if parent else "FRESH",
                    parent_cut_id=parent,
                )
            )
            audit(db, tenant, company, generation.id, "requested")
