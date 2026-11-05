"""Operator commands for the local provider.

    python -m identity.local_auth.cli rotate-key     # start signing with a new key
    python -m identity.local_auth.cli retire-keys    # stop publishing keys whose tokens expired
    python -m identity.local_auth.cli purge          # delete spent and expired rows
    python -m identity.local_auth.cli reset-setup-administrator
                                                      # forget a first-run administrator never used
    python -m identity.local_auth.cli adopt-users [--email ADDRESS ...] [--all]
                                                      # move existing accounts to local sign-in

Rotation is two steps on purpose. ``rotate-key`` makes a new key the signer and keeps the old public
key published, so every token already issued still verifies. ``retire-keys`` removes a rotated-out
key only once the longest token it could have signed has expired. Neither prints a key.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json

from billing_platform.db import unfiltered
from billing_platform.db.session import create_engine, create_session_factory
from billing_platform.db.types import utcnow
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.config import Settings
from identity.local_auth.adoption import Adopted, adopt_users, operator_settings
from identity.local_auth.service import LocalAuth
from identity.models import PlatformInstallation, User
from identity.models.local_auth import (
    PATH_PLATFORM,
    LocalAuthorization,
    LocalCredential,
    LocalIdentity,
    LocalRecoveryToken,
    LocalRefreshToken,
)

#: How long after expiry a spent row is kept — long enough to explain a refused token, no longer.
KEEP = dt.timedelta(days=7)


async def rotate_key(factory: async_sessionmaker[AsyncSession], service: LocalAuth) -> str:
    async with factory() as db:
        row = await service.keys.generate(db)
        await db.commit()
        return row.kid


async def retire_keys(factory: async_sessionmaker[AsyncSession], service: LocalAuth) -> int:
    """A rotated-out key is kept for one more access-token lifetime, plus a minute of clock skew."""
    longest = dt.timedelta(seconds=service.settings.access_token_seconds + 60)
    async with factory() as db:
        retired = await service.keys.retire_expired(db, longest_token=longest)
        await db.commit()
        return retired


async def purge(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    cutoff = utcnow() - KEEP
    counts: dict[str, int] = {}
    async with factory() as db:
        for name, statement in (
            (
                "authorizations",
                delete(LocalAuthorization).where(LocalAuthorization.expires_at < cutoff),
            ),
            (
                "recovery_tokens",
                delete(LocalRecoveryToken).where(
                    or_(LocalRecoveryToken.expires_at < cutoff, LocalRecoveryToken.used_at < cutoff)
                ),
            ),
            (
                "refresh_tokens",
                delete(LocalRefreshToken).where(
                    or_(
                        LocalRefreshToken.expires_at < cutoff, LocalRefreshToken.revoked_at < cutoff
                    )
                ),
            ),
        ):
            result = await db.execute(statement)
            counts[name] = int(getattr(result, "rowcount", 0) or 0)
        await db.commit()
    return counts


async def reset_setup_administrator(factory: async_sessionmaker[AsyncSession]) -> str:
    """Forget the first-run administrator account so setup can create it again.

    Setup makes the administrator's account first and finishes only once that person has signed in.
    A mistyped password before then leaves an account nobody can use and, because setup only creates
    one, no way to correct it. This removes it — but only while setup is still open, and never an
    account a user row already points at.
    """
    async with factory() as db:
        with unfiltered():
            completed = await db.scalar(
                select(PlatformInstallation.completed_at).where(
                    PlatformInstallation.key == "platform"
                )
            )
            if completed is not None:
                return "Setup has completed: the administrator is an ordinary account now."
            identities = list(
                await db.scalars(select(LocalIdentity).where(LocalIdentity.path == PATH_PLATFORM))
            )
            linked = [
                identity
                for identity in identities
                if await db.scalar(select(User.id).where(User.authentik_sub == identity.sub))
            ]
            if linked:
                return "An administrator account is already linked to a user. Nothing was done."
        for identity in identities:
            for model in (LocalRefreshToken, LocalAuthorization, LocalRecoveryToken):
                await db.execute(delete(model).where(model.identity_seq == identity.seq))
            await db.execute(
                delete(LocalCredential).where(LocalCredential.identity_seq == identity.seq)
            )
            await db.delete(identity)
        await db.commit()
        return f"Removed {len(identities)} unused setup administrator account(s)."


def adoption_report(settings: Settings, adopted: list[Adopted]) -> str:
    """What to tell the operator. The links are secrets: they appear here and nowhere else."""
    moved = [item for item in adopted if item.link]
    lines = []
    if moved:
        minutes = settings.local_auth.recovery_token_seconds // 60 if settings.local_auth else 10
        lines.append(
            f"Moved {len(moved)} account(s) to local sign-in. Hand each link over privately: "
            f"it works once and lasts {minutes} minutes. If one expires, create another from the "
            "Console (the platform access page for a platform administrator, the user's page for "
            "anyone else)."
        )
        for item in moved:
            role = " [platform administrator]" if item.platform_operator else ""
            lines.append(f"  {item.email}{role}\n    {item.link}")
    skipped = [item for item in adopted if item.skipped]
    if skipped:
        lines.append(f"Skipped {len(skipped)}:")
        lines.extend(f"  {item.email}: {item.skipped}" for item in skipped)
    if not adopted:
        lines.append(
            "Nobody to move: no platform administrator is recorded and none is configured. "
            "Name accounts with --email, or use --all."
        )
    mapping = operator_settings(settings, adopted)
    if mapping is not None:
        lines.append(
            "IDENTITY_PLATFORM_OPERATORS names operators by their old subject. Replace it with "
            f"this, then restart Identity:\n  {json.dumps(mapping, separators=(',', ':'))}"
        )
    return "\n".join(lines)


async def run(command: str, emails: list[str] | None = None, everyone: bool = False) -> str:
    settings = Settings()  # type: ignore[call-arg]
    if settings.auth_provider != "local" or settings.local_auth is None:
        return "The local provider is not configured; nothing was done."
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    service = LocalAuth(settings.local_auth)
    try:
        if command == "rotate-key":
            return f"New signing key {await rotate_key(factory, service)} is active."
        if command == "retire-keys":
            return f"Retired {await retire_keys(factory, service)} key(s)."
        if command == "reset-setup-administrator":
            return await reset_setup_administrator(factory)
        if command == "adopt-users":
            return adoption_report(
                settings,
                await adopt_users(
                    factory, service, settings, emails=emails or (), everyone=everyone
                ),
            )
        counts = await purge(factory)
        return (
            "Deleted "
            + ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in counts.items())
            + "."
        )
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "command",
        choices=("rotate-key", "retire-keys", "purge", "reset-setup-administrator", "adopt-users"),
    )
    parser.add_argument(
        "--email", action="append", default=[], help="adopt this account (repeatable)"
    )
    parser.add_argument(
        "--all", action="store_true", dest="everyone", help="adopt every active user"
    )
    options = parser.parse_args(argv)
    print(asyncio.run(run(options.command, options.email, options.everyone)))  # noqa: T201 - a command-line tool
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
