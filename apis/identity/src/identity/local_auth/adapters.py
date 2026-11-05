"""The local provider behind the interfaces the Authentik adapters already satisfy.

Account review, tenant-administrator provisioning and administrator recovery were written against
an *external* provider, so they speak in its vocabulary (a numeric id, a uuid, a path, "active" and
"verified"). These classes answer in the same vocabulary from the local tables, which is what lets
the review state machine, its reconciliation and its audit run unchanged over local accounts.

Each method works in its own short transaction, exactly as a call to an external service would:
the caller holds locks on its own rows and must not have its commit decided by ours.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import uuid
from typing import Any, Literal

from billing_platform.db import unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.domain.account_review import Applicant, eligible
from identity.local_auth import domain, offload
from identity.local_auth.service import LocalAuth
from identity.models import AccountReviewCommand
from identity.models.local_auth import (
    PATH_ADMINISTRATORS,
    PATH_PENDING,
    PATH_PLATFORM,
    LocalCredential,
    LocalIdentity,
)
from identity.services.account_provider import AccountProviderUnavailableError
from identity.services.administrator_provider import AdministratorProviderUnavailableError
from identity.services.administrator_recovery import AdministratorRecoveryUnavailableError

_SUB = re.compile(r"^[0-9a-f]{64}$")
PAGE_SIZE = 100


def _applicant(row: LocalIdentity) -> Applicant:
    return Applicant(
        provider_id=row.seq,
        provider_uuid=row.uid,
        name=row.name,
        username=row.username,
        email=row.email,
        path=row.path,
        user_type="external",
        is_active=row.status == "active",
        verified=row.email_verified_at is not None,
        groups=(),
        roles=(),
        country_code=row.country_code,
        state_code=row.state_code,
        workspace_name=row.workspace_name,
    )


def _raw(row: LocalIdentity) -> dict[str, Any]:
    """The provider-shaped record the reconciler inspects for its own command marker."""
    return {
        "pk": row.seq,
        "uuid": str(row.uid),
        "sub": row.sub,
        "attributes": {"billing_account_review_command": row.review_command},
    }


class LocalAccountProvider:
    """Pending sign-ups, as the review workflow reads and decides them."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def page(self, page: int = 1) -> tuple[list[Applicant], bool]:
        async with self.factory() as db:
            rows = (
                await db.scalars(
                    select(LocalIdentity)
                    .where(LocalIdentity.path == PATH_PENDING)
                    .order_by(LocalIdentity.seq.desc())
                    .offset((page - 1) * PAGE_SIZE)
                    .limit(PAGE_SIZE + 1)
                )
            ).all()
        applicants = [_applicant(row) for row in rows[:PAGE_SIZE]]
        return [row for row in applicants if eligible(row)], len(rows) > PAGE_SIZE

    async def pending_email(self, email: str) -> list[Applicant]:
        async with self.factory() as db:
            rows = (
                await db.scalars(
                    select(LocalIdentity).where(
                        LocalIdentity.path == PATH_PENDING,
                        LocalIdentity.email == email.strip().lower(),
                        LocalIdentity.status == "pending",
                        LocalIdentity.email_verified_at.is_(None),
                    )
                )
            ).all()
        return [row for row in map(_applicant, rows) if eligible(row)]

    async def read(self, provider_id: int) -> tuple[Applicant, dict[str, Any]]:
        async with self.factory() as db:
            identity = await db.get(LocalIdentity, provider_id)
        if identity is None:
            raise AccountProviderUnavailableError(
                "This account is outside the supported registration scope."
            )
        applicant = _applicant(identity)
        if not eligible(applicant):
            raise AccountProviderUnavailableError(
                "This account is outside the supported registration scope."
            )
        return applicant, _raw(identity)

    def subject(self, raw: dict[str, Any]) -> str:
        value = raw.get("sub")
        if not isinstance(value, str) or _SUB.fullmatch(value) is None:
            raise AccountProviderUnavailableError("Registration subject could not be confirmed.")
        return value

    async def apply(
        self,
        provider_id: int,
        raw: dict[str, Any],
        *,
        active: bool,
        verified: bool,
        command_id: uuid.UUID,
    ) -> None:
        async with self.factory() as db:
            identity = await db.get(LocalIdentity, provider_id)
            if identity is None or str(identity.uid) != raw.get("uuid"):
                raise AccountProviderUnavailableError("Registration identity changed.")
            # By primary key and read-only: the command's tenant is the platform tenant the caller
            # already holds, and this adapter must not depend on that context being set.
            with unfiltered():
                action = await db.scalar(
                    select(AccountReviewCommand.action).where(AccountReviewCommand.id == command_id)
                )
            if active:
                identity.status = "active"
            elif action == "reopen":
                identity.status = "pending"
            else:
                # A rejected sign-up must not read as "waiting for approval" at sign-in.
                identity.status = "disabled"
            identity.email_verified_at = (
                (identity.email_verified_at or utcnow()) if verified else None
            )
            identity.review_command = str(command_id)
            await db.commit()


class LocalAdministratorProvider:
    """Tenant-administrator accounts created by an operator, activated once the tenant exists."""

    @staticmethod
    def username_for(email: str) -> str:
        # Stable across request keys, so concurrent creates for one email cannot make two accounts.
        return "bill-admin-" + hashlib.sha256(email.strip().casefold().encode()).hexdigest()[:32]

    def __init__(self, factory: async_sessionmaker[AsyncSession], service: LocalAuth) -> None:
        self.factory, self.service = factory, service

    @staticmethod
    def _row(identity: LocalIdentity) -> dict[str, Any]:
        return {
            "pk": identity.seq,
            "uid": identity.sub,
            "username": identity.username,
            "name": identity.name,
            "email": identity.email,
            "type": "external",
            "path": identity.path,
            "is_active": identity.status == "active",
            "is_superuser": False,
            "groups": [],
            "roles": [],
            "attributes": {
                "billing_email_verified": identity.email_verified_at is not None,
                "billing_tenant_provision_command": identity.provision_command,
            },
        }

    @staticmethod
    def confirm(row: dict[str, Any], email: str) -> tuple[int, str]:
        attributes = row.get("attributes")
        if (
            type(row.get("pk")) is not int
            or not isinstance(row.get("uid"), str)
            or _SUB.fullmatch(row["uid"]) is None
            or not isinstance(row.get("email"), str)
            or row["email"].strip().casefold() != email.strip().casefold()
            or row.get("is_active") is not True
            or not isinstance(attributes, dict)
            or attributes.get("billing_email_verified") is not True
        ):
            raise ConflictError("The selected account is not an active verified user.")
        return int(row["pk"]), str(row["uid"])

    async def by_email(self, email: str) -> dict[str, Any] | None:
        async with self.factory() as db:
            identity = await db.scalar(
                select(LocalIdentity).where(LocalIdentity.email == email.strip().lower())
            )
        return None if identity is None else self._row(identity)

    async def create(
        self, *, email: str, name: str, password: str, marker: uuid.UUID
    ) -> tuple[str, str]:
        username = self.username_for(email)
        async with self.factory() as db:
            existing = await db.scalar(
                select(LocalIdentity).where(LocalIdentity.email == email.strip().lower())
            )
            if existing is None:
                # Inactive until the tenant commits, so a database failure cannot leave a
                # sign-in-capable orphan behind.
                created = await self.service.create_administrator(
                    db,
                    name=name,
                    email=email,
                    password=password,
                    path=PATH_ADMINISTRATORS,
                    active=False,
                    provision_command=str(marker),
                    username=username,
                )
                await db.commit()
                return created.username, created.sub
            attributes_ok = (
                existing.username == username
                and existing.path == PATH_ADMINISTRATORS
                and existing.provision_command == str(marker)
                and existing.email_verified_at is not None
            )
            if not attributes_ok:
                raise ConflictError(
                    "An account already uses this email. Select it instead."
                    if existing.username != username
                    else "The provisioning account changed. Review it before retrying."
                )
            if existing.status != "active":
                credential = await db.get(LocalCredential, existing.seq)
                problem = domain.password_problem(password)
                if problem or credential is None:
                    raise ConflictError(
                        "The provisioning account changed. Review it before retrying."
                    )
                credential.password_hash = await offload.hash_password(password)
                credential.password_changed_at = utcnow()
                await db.commit()
            return existing.username, existing.sub

    async def activate(self, *, email: str, marker: uuid.UUID, subject: str) -> None:
        async with self.factory() as db:
            identity = await db.scalar(
                select(LocalIdentity).where(LocalIdentity.email == email.strip().lower())
            )
            if identity is None:
                raise AdministratorProviderUnavailableError("Provisioned account disappeared.")
            if (
                identity.provision_command != str(marker)
                or identity.path != PATH_ADMINISTRATORS
                or identity.email_verified_at is None
            ):
                raise ConflictError("The provisioned account changed before activation.")
            if identity.sub != subject:
                raise ConflictError("The account identity changed before activation.")
            if identity.status != "active":
                identity.status = "active"
                await db.commit()


class LocalRecoveryProvider:
    """Operator-issued one-time recovery links. Nothing leaves the installation."""

    @staticmethod
    def subject_field(subject: str | uuid.UUID) -> str | None:
        return "sub" if _SUB.fullmatch(str(subject)) else None

    def __init__(self, factory: async_sessionmaker[AsyncSession], service: LocalAuth) -> None:
        self.factory, self.service = factory, service

    async def recover(
        self,
        subject: str | uuid.UUID,
        delivery: Literal["link", "email"],
        expected_email: str,
    ) -> tuple[str | None, dt.datetime]:
        if delivery == "email":
            raise AdministratorRecoveryUnavailableError(
                "Recovery email needs configured delivery. Create a recovery link instead."
            )
        unusable = AdministratorRecoveryUnavailableError(
            "This sign-in account cannot use billing password recovery."
        )
        async with self.factory() as db:
            identity = await db.scalar(
                select(LocalIdentity).where(LocalIdentity.sub == str(subject))
            )
            if (
                identity is None
                or identity.status != "active"
                or identity.email_verified_at is None
                or identity.path not in (PATH_ADMINISTRATORS, PATH_PLATFORM, PATH_PENDING)
                or identity.email != expected_email.strip().lower()
            ):
                raise unusable
            token, expires = await self.service.issue_recovery(db, identity, issued_by=None)
            await db.commit()
        return self.service.recovery_url(token), expires
