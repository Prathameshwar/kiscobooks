"""Configuration history is authoritative; locale fallback needs executable content."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import NotificationTemplate, TemplateVariant, UseCaseBinding
from notification.tasks.consume import _resolve_template_version
from tests.notif_seed import seed_email_route


@pytest.mark.asyncio
async def test_ended_assignment_prevents_legacy_fallback(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    now = utcnow()
    with tenant_scope(tenant_a):
        template = (await session.scalars(select(NotificationTemplate))).one()
        session.add(
            UseCaseBinding(
                tenant_id=tenant_a,
                company_id=company,
                event_key="invoice.posted",
                trigger_key="accounting.invoice.posted",
                channel="email",
                template_id=template.id,
                valid_from=now - dt.timedelta(days=2),
                valid_to=now - dt.timedelta(days=1),
            )
        )
        await session.commit()
        assert (
            await _resolve_template_version(
                session,
                company_id=company,
                event_key="invoice.posted",
                trigger_key="accounting.invoice.posted",
                channel="email",
                locale=None,
                now=now,
            )
            is None
        )


@pytest.mark.asyncio
async def test_unactivated_locale_uses_executable_default(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    with tenant_scope(tenant_a):
        template = (await session.scalars(select(NotificationTemplate))).one()
        session.add(
            TemplateVariant(
                tenant_id=tenant_a, template_id=template.id, channel="email", locale="fr"
            )
        )
        await session.commit()
        result = await _resolve_template_version(
            session,
            company_id=company,
            event_key="invoice.posted",
            channel="email",
            locale="fr",
            now=utcnow(),
        )
        assert result is not None
        variant = await session.get(TemplateVariant, result.template_variant_id)
        assert variant is not None and variant.locale == "en-IN"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expired,reason",
    [(True, "request_expired"), (False, "template_variables_or_rendering_invalid")],
)
async def test_planning_failures_remain_visible(
    session: AsyncSession, tenant_a: uuid.UUID, expired: bool, reason: str
) -> None:
    from notification.models import PlanningOutcome
    from notification.tasks.consume import handle_send_command
    from tests.notif_seed import CIPHER, KEY_REF, envelope

    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    message = envelope(tenant_a, company, subject)
    message.payload["variables"] = {}
    if expired:
        message.payload["expires_at"] = (utcnow() - dt.timedelta(minutes=1)).isoformat()
    with tenant_scope(tenant_a):
        result = await handle_send_command(session, message, cipher=CIPHER, key_ref=KEY_REF)
        await session.commit()
        assert result.deliveries_created == 0
        outcome = (await session.scalars(select(PlanningOutcome))).one()
        assert outcome.reason_code == reason
