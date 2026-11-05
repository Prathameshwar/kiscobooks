"""Install the Notification-owned invitation template; configure an email route separately."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import uuid

from billing_platform.constants import SCOPE_ALL
from billing_platform.db import create_engine, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.config import Settings
from notification.models import (
    NotificationTemplate,
    TemplateActivation,
    TemplateVariant,
    TemplateVersion,
)
from notification.ownership import session_factory as notification_session_factory


async def install(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    existing = await db.scalar(
        select(NotificationTemplate.id).where(
            NotificationTemplate.company_id == SCOPE_ALL,
            NotificationTemplate.key == "identity.invitation",
        )
    )
    if existing is not None:
        return existing
    template, variant, version = uuid7(), uuid7(), uuid7()
    subject = "Your workspace invitation"
    body = (
        "You have been invited to a workspace. "
        "Sign in with this email address to accept: {{ invitation_url }}"
    )
    db.add(
        NotificationTemplate(
            id=template,
            tenant_id=tenant_id,
            company_id=SCOPE_ALL,
            key="identity.invitation",
            event_key="user.invited",
            category="security",
            default_locale="en",
            variable_schema={
                "type": "object",
                "required": ["invitation_url"],
                "properties": {"invitation_url": {"type": "string"}},
            },
        )
    )
    await db.flush()
    db.add(
        TemplateVariant(
            id=variant, tenant_id=tenant_id, template_id=template, channel="email", locale="en"
        )
    )
    await db.flush()
    db.add(
        TemplateVersion(
            id=version,
            tenant_id=tenant_id,
            template_variant_id=variant,
            version=1,
            subject_text=subject,
            body_text=body,
            content_sha256=hashlib.sha256((subject + body).encode()).digest(),
        )
    )
    await db.flush()
    db.add(
        TemplateActivation(
            id=uuid7(),
            tenant_id=tenant_id,
            template_variant_id=variant,
            template_version_id=version,
            valid_from=utcnow(),
            activation_reason="Identity invitation bootstrap",
        )
    )
    emit(
        db,
        tenant_id=tenant_id,
        aggregate_type="notification_template",
        aggregate_id=template,
        event_type="notification.invitation_template_installed",
        payload={"template_id": str(template)},
    )
    await db.flush()
    return template


async def run(tenant_id: uuid.UUID) -> None:
    settings = Settings()  # type: ignore[call-arg]  # required settings are provided in environment
    engine = create_engine(settings.database_url)
    try:
        with tenant_scope(tenant_id):
            async with notification_session_factory(engine)() as db, db.begin():
                await install(db, tenant_id)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", type=uuid.UUID, required=True)
    asyncio.run(run(parser.parse_args().tenant))
