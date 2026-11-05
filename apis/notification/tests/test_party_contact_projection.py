"""Accounting contact snapshots are purpose-specific and monotonic."""

import datetime as dt
import uuid
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import PartyEndpointCheckpoint, RecipientEndpoint
from notification.security import AesGcmCipher
from notification.tasks.party_contacts import project_snapshot

KEY = b"k" * 32


def snapshot(
    tenant: uuid.UUID,
    company: uuid.UUID,
    party: uuid.UUID,
    version: int,
    destinations: list[dict[str, Any]],
) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=uuid7(),
        tenant_id=tenant,
        event_type="accounting.party_contact.snapshot",
        schema_version=1,
        occurred_at=dt.datetime.now(dt.UTC),
        payload={
            "company_id": str(company),
            "party_id": str(party),
            "source_version": version,
            "destinations": destinations,
        },
    )


@pytest.mark.asyncio
async def test_party_endpoint_projection_tombstones_and_stale_replay(
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    company, party = uuid7(), uuid7()
    first = snapshot(
        tenant_a,
        company,
        party,
        3,
        [
            {
                "purpose": "INVOICING",
                "channel": "email",
                "destination": "buyer@example.test",
                "locale": "en-IN",
            }
        ],
    )
    await project_snapshot(
        session,
        first,
        cipher=AesGcmCipher(KEY),
        destination_key=KEY,
    )
    await session.commit()
    with tenant_scope(tenant_a):
        current = await session.scalar(
            select(RecipientEndpoint).where(
                RecipientEndpoint.subject_type == "party_invoicing",
                RecipientEndpoint.subject_id == party,
            )
        )
        assert current is not None and current.is_active
        assert current.destination_masked != "buyer@example.test"
        assert current.destination_ciphertext is not None
        assert (
            AesGcmCipher(KEY).decrypt(
                current.destination_ciphertext,
                associated_data=current.id.bytes,
            )
            == b"buyer@example.test"
        )
    retired = snapshot(tenant_a, company, party, 4, [])
    await project_snapshot(
        session,
        retired,
        cipher=AesGcmCipher(KEY),
        destination_key=KEY,
    )
    await session.commit()
    await project_snapshot(
        session,
        first,
        cipher=AesGcmCipher(KEY),
        destination_key=KEY,
    )
    await session.commit()
    with tenant_scope(tenant_a):
        endpoint = await session.get(RecipientEndpoint, current.id)
        checkpoint = await session.scalar(
            select(PartyEndpointCheckpoint).where(
                PartyEndpointCheckpoint.company_id == company,
                PartyEndpointCheckpoint.party_id == party,
                PartyEndpointCheckpoint.purpose == "INVOICING",
                PartyEndpointCheckpoint.channel == "email",
            )
        )
        assert endpoint is not None and not endpoint.is_active
        assert checkpoint is not None and checkpoint.source_version == 4
        assert checkpoint.endpoint_id is None


@pytest.mark.asyncio
async def test_same_party_and_destination_in_two_companies_stay_separate(
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    company_a, company_b, party = uuid7(), uuid7(), uuid7()
    destination = [
        {
            "purpose": "INVOICING",
            "channel": "email",
            "destination": "shared@example.test",
            "locale": "en-IN",
        }
    ]
    for company in (company_a, company_b):
        await project_snapshot(
            session,
            snapshot(tenant_a, company, party, 1, destination),
            cipher=AesGcmCipher(KEY),
            destination_key=KEY,
        )
        await session.commit()
    with tenant_scope(tenant_a):
        rows = list(
            (
                await session.scalars(
                    select(PartyEndpointCheckpoint).where(
                        PartyEndpointCheckpoint.party_id == party,
                        PartyEndpointCheckpoint.purpose == "INVOICING",
                        PartyEndpointCheckpoint.channel == "email",
                    )
                )
            ).all()
        )
        assert len(rows) == 2
        assert rows[0].endpoint_id != rows[1].endpoint_id
        from notification.tasks.consume import _active_endpoint

        first = await _active_endpoint(
            session,
            subject_type="party_invoicing",
            subject_id=party,
            channel="email",
            company_id=company_a,
        )
        second = await _active_endpoint(
            session,
            subject_type="party_invoicing",
            subject_id=party,
            channel="email",
            company_id=company_b,
        )
        assert first is not None and second is not None
        assert first.id != second.id
