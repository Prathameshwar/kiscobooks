"""Project purpose-specific Accounting party destinations to Notification."""

from __future__ import annotations

import uuid

from billing_platform.db import create_engine, create_session_factory, tenant_scope, unfiltered
from billing_platform.outbox import emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models import masters as m

PURPOSES = ("GENERAL", "INVOICING", "PAYMENTS", "DELIVERY")


def _phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(char for char in value if '0' <= char <= '9')
    if len(digits) == 10:
        digits = "91" + digits
    if 10 <= len(digits) <= 15 and digits[0] != "0":
        return "+" + digits
    return None


async def _emit_snapshot(
    db: AsyncSession, *, tenant_id: uuid.UUID, company_id: uuid.UUID,
    party_id: uuid.UUID, source_version: int,
) -> None:
    rows = list(
        (await db.execute(
            select(m.PartyContactUse, m.PartyContact)
            .join(
                m.PartyContact,
                (m.PartyContact.id == m.PartyContactUse.contact_id)
                & (m.PartyContact.company_id == m.PartyContactUse.company_id),
            )
            .where(
                m.PartyContactUse.company_id == company_id,
                m.PartyContactUse.party_id == party_id,
                m.PartyContactUse.status == "ACTIVE",
                m.PartyContact.status == "ACTIVE",
            )
            .order_by(
                m.PartyContactUse.is_default.desc(),
                m.PartyContactUse.id.asc(),
            )
        )).all()
    )
    destinations: list[dict[str, str]] = []
    for purpose in PURPOSES:
        choices = [(use, contact) for use, contact in rows if use.purpose == purpose]
        for channel in ("email", "sms", "whatsapp"):
            for _, contact in choices:
                destination = (
                    contact.email.strip().lower() if channel == "email" and contact.email
                    else _phone(contact.mobile or contact.phone)
                    if channel in {"sms", "whatsapp"} else None
                )
                if destination:
                    destinations.append({
                        "purpose": purpose,
                        "channel": channel,
                        "destination": destination,
                        "locale": contact.language or "en-IN",
                    })
                    break
    emit(
        db,
        aggregate_type="accounting.party",
        aggregate_id=party_id,
        event_type="accounting.party_contact.snapshot",
        tenant_id=tenant_id,
        payload={
            "company_id": str(company_id),
            "party_id": str(party_id),
            "source_version": source_version,
            "destinations": destinations,
        },
    )



async def emit_party_snapshot(db: AsyncSession, access: Access, party_id: uuid.UUID) -> None:
    """Emit the full current selection after a contact/use mutation commits."""
    setup = await db.scalar(select(m.AccountingSetup).where(
        m.AccountingSetup.company_id == access.context.company_id
    ))
    if setup is None:
        raise ValueError("Accounting setup is required for party contact projection")
    await _emit_snapshot(
        db, tenant_id=access.actor.tenant_id,
        company_id=access.context.company_id,
        party_id=party_id, source_version=setup.generation,
    )


async def backfill_company(
    db: AsyncSession, *, tenant_id: uuid.UUID, company_id: uuid.UUID,
    after_party_id: uuid.UUID | None = None, limit: int = 200,
) -> tuple[int, uuid.UUID | None]:
    """Emit one bounded page of fresh snapshots after the company-fence migration."""
    if not 1 <= limit <= 1000:
        raise ValueError("backfill limit must be between 1 and 1000")
    with tenant_scope(tenant_id):
        setup = await db.scalar(select(m.AccountingSetup).where(
            m.AccountingSetup.company_id == company_id
        ).with_for_update())
        if setup is None:
            raise ValueError("Accounting setup is required for party contact backfill")
        query = select(m.PartyContactUse.party_id).where(
            m.PartyContactUse.company_id == company_id,
        )
        if after_party_id is not None:
            query = query.where(m.PartyContactUse.party_id > after_party_id)
        parties = list((await db.scalars(
            query.distinct().order_by(m.PartyContactUse.party_id).limit(limit)
        )).all())
        if not parties:
            return 0, None
        setup.generation += 1
        await db.flush()
        for party_id in parties:
            await _emit_snapshot(
                db, tenant_id=tenant_id, company_id=company_id,
                party_id=party_id, source_version=setup.generation,
            )
        return len(parties), parties[-1]


async def run_backfill(database_url: str) -> int:
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    total = 0
    try:
        with unfiltered():
            async with factory() as db:
                companies = list((await db.execute(
                    select(m.AccountingSetup.tenant_id, m.AccountingSetup.company_id)
                    .join(m.PartyContactUse, (
                        m.PartyContactUse.tenant_id == m.AccountingSetup.tenant_id
                    ) & (
                        m.PartyContactUse.company_id == m.AccountingSetup.company_id
                    )).distinct()
                )).all())
        for tenant_id, company_id in companies:
            after_party_id = None
            while True:
                with tenant_scope(tenant_id):
                    async with factory() as db, db.begin():
                        count, next_id = await backfill_company(
                            db, tenant_id=tenant_id, company_id=company_id,
                            after_party_id=after_party_id,
                        )
                total += count
                if next_id is None:
                    break
                after_party_id = next_id
    finally:
        await engine.dispose()
    return total
