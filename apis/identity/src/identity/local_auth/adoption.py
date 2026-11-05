"""Moving people who already have an account from another sign-in provider to the local one.

Credentials are never moved between providers (docs/local-auth.md §8): an Authentik password is
Authentik's. What *can* move is the person's place in the platform. A ``user`` row is linked to its
sign-in by one subject (``user.authentik_sub``); under the local provider nobody holds a subject the
old rows point at, so every existing account — the platform administrator first of all — can no
longer sign in, and a fresh sign-up with the same email is a different account that nobody with
authority can approve.

Adoption fixes that for the people an operator names, with the operator's own database access as the
authority. For each one it creates a local account (active, email verified: the platform already
vouched for it), gives it a password nobody knows, points the existing ``user`` row at the new
subject so every role, company and history stays attached, ends every session the old subject might
still hold, and issues a one-time link through which the person chooses a password.

It never decides who is trusted: the default is the platform's own operators, and anyone else has to
be named (``--email``) or asked for outright (``--all``).
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.api.auth import Actor
from identity.config import Settings
from identity.local_auth import domain
from identity.local_auth.service import LocalAuth
from identity.models import PlatformInstallation, User
from identity.models.local_auth import PATH_ADMINISTRATORS, PATH_PLATFORM, LocalIdentity
from identity.services.audit import record


@dataclass(frozen=True, slots=True)
class Adopted:
    """One person's outcome. ``link`` is a secret: shown once, never stored in the clear."""

    email: str
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    platform_operator: bool
    #: The subject the account now signs in under (not a secret). ``None`` if it was skipped.
    new_subject: str | None = None
    link: str | None = None
    skipped: str | None = None


async def _operators(
    db: AsyncSession, settings: Settings
) -> tuple[set[uuid.UUID], uuid.UUID | None]:
    """The platform's operators: those configured, and the administrator setup recorded."""
    with unfiltered():
        installation = await db.scalar(
            select(PlatformInstallation).where(PlatformInstallation.key == "platform")
        )
    recorded = (
        installation.administrator_id
        if installation is not None and installation.completed_at is not None
        else None
    )
    operators = set(settings.platform_operators.values())
    if recorded is not None:
        operators.add(recorded)
    return operators, recorded


async def adopt_users(
    factory: async_sessionmaker[AsyncSession],
    service: LocalAuth,
    settings: Settings,
    *,
    emails: Sequence[str] = (),
    everyone: bool = False,
) -> list[Adopted]:
    """Adopt the platform operators (default), the named emails, or every active user."""
    async with factory() as db:
        operators, recorded = await _operators(db, settings)
        query = select(User.id).where(User.status == "active", User.authentik_sub.is_not(None))
        if emails:
            query = query.where(func.lower(User.email).in_({e.strip().lower() for e in emails}))
        elif not everyone:
            if not operators:
                return []
            query = query.where(User.id.in_(operators))
        with unfiltered():
            ids = list(await db.scalars(query.order_by(User.created_at, User.id)))
            local_subjects = set(await db.scalars(select(LocalIdentity.sub)))

    results: list[Adopted] = []
    for user_id in ids:
        # One transaction per person: a problem with one account must not undo the others.
        async with factory() as db:
            with unfiltered():
                user = await db.get(User, user_id)
            if user is None or user.authentik_sub is None:
                continue
            operator = user.id in operators
            if user.authentik_sub in local_subjects:
                results.append(
                    Adopted(
                        user.email,
                        user.id,
                        user.tenant_id,
                        operator,
                        skipped="already signs in locally",
                    )
                )
                continue
            address = domain.clean_email(user.email)
            if address is None:
                results.append(
                    Adopted(
                        user.email,
                        user.id,
                        user.tenant_id,
                        operator,
                        skipped="the email is not usable",
                    )
                )
                continue
            with unfiltered():
                taken = await db.scalar(
                    select(LocalIdentity.seq).where(LocalIdentity.email == address)
                )
            if taken is not None:
                results.append(
                    Adopted(
                        user.email,
                        user.id,
                        user.tenant_id,
                        operator,
                        skipped="another local account uses this email; review it first",
                    )
                )
                continue
            name = (user.display_name or "").strip()[:100] or address.split("@")[0]
            try:
                identity = await service.create_administrator(
                    db,
                    name=name,
                    email=address,
                    # Nobody ever sees this: the person chooses their own through the link below.
                    password=secrets.token_urlsafe(24),
                    path=PATH_PLATFORM if operator else PATH_ADMINISTRATORS,
                )
            except PlatformError as exc:
                await db.rollback()
                results.append(
                    Adopted(user.email, user.id, user.tenant_id, operator, skipped=exc.message)
                )
                continue
            now = utcnow()
            with tenant_scope(user.tenant_id):
                user.authentik_sub = identity.sub
                # Whatever the old subject was still holding is over.
                user.tokens_valid_after_at = now
                await db.flush()
            if recorded == user.id:
                with unfiltered():
                    installation = await db.scalar(
                        select(PlatformInstallation)
                        .where(PlatformInstallation.key == "platform")
                        .with_for_update()
                    )
                if installation is not None:
                    installation.administrator_subject = identity.sub
            record(
                db,
                Actor(user.tenant_id, user.id),
                action="user.sign_in_provider_changed",
                entity="user",
                entity_id=user.id,
                reason="moved to local sign-in by an operator command",
            )
            token, _ = await service.issue_recovery(db, identity, issued_by=None)
            await db.commit()
            results.append(
                Adopted(
                    user.email,
                    user.id,
                    user.tenant_id,
                    operator,
                    new_subject=identity.sub,
                    link=service.recovery_url(token),
                )
            )
            local_subjects.add(identity.sub)
    return results


def operator_settings(settings: Settings, adopted: Sequence[Adopted]) -> dict[str, str] | None:
    """The ``platform_operators`` mapping with adopted operators' new subjects, if it must change.

    The mapping is configuration (``IDENTITY_PLATFORM_OPERATORS``): subject -> user id. An operator
    configured there is recognised by the *old* subject, so after adoption the setting has to be
    updated by hand — adoption edits the database, never the environment.
    """
    moved = {item.user_id: item.new_subject for item in adopted if item.new_subject}
    if not set(settings.platform_operators.values()) & set(moved):
        return None
    return {
        moved.get(user_id) or subject: str(user_id)
        for subject, user_id in settings.platform_operators.items()
    }
