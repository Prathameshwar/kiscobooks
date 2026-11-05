"""Which identity provider owns credentials, chosen once for the installation.

``AUTH_PROVIDER`` is ``local`` (Identity's own OpenID Connect provider) or ``authentik``. Account
review, tenant-administrator provisioning and administrator recovery speak to a provider through
the three small interfaces below; the Authentik adapters and the local ones both satisfy them, and
these factories are the only place that decides which is used.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal, Protocol

import httpx
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.config import Settings
from identity.domain.account_review import Applicant


class AccountDirectory(Protocol):
    """Sign-ups awaiting review, and the verdict written back to them."""

    async def page(self, page: int = 1) -> tuple[list[Applicant], bool]: ...

    async def pending_email(self, email: str) -> list[Applicant]: ...

    async def read(self, provider_id: int) -> tuple[Applicant, dict[str, Any]]: ...

    def subject(self, raw: dict[str, Any]) -> str: ...

    async def apply(
        self,
        provider_id: int,
        raw: dict[str, Any],
        *,
        active: bool,
        verified: bool,
        command_id: uuid.UUID,
    ) -> None: ...


class AdministratorDirectory(Protocol):
    """Tenant-administrator accounts created by a platform operator."""

    def confirm(self, row: dict[str, Any], email: str) -> tuple[int, str]: ...

    async def by_email(self, email: str) -> dict[str, Any] | None: ...

    async def create(
        self, *, email: str, name: str, password: str, marker: uuid.UUID
    ) -> tuple[str, str]: ...

    async def activate(self, *, email: str, marker: uuid.UUID, subject: str) -> None: ...


class RecoveryDirectory(Protocol):
    """Password recovery for a tenant administrator, started by a platform operator."""

    async def recover(
        self,
        subject: str | uuid.UUID,
        delivery: Literal["link", "email"],
        expected_email: str,
    ) -> tuple[str | None, dt.datetime]: ...


def _is_local(settings: Settings) -> bool:
    return settings.auth_provider == "local"


def build_account_directory(
    settings: Settings, http: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> AccountDirectory:
    if _is_local(settings):
        from identity.local_auth.adapters import LocalAccountProvider

        return LocalAccountProvider(factory)
    from identity.services.account_provider import AccountProvider

    return AccountProvider(settings, http)


def account_directory(request: Request) -> AccountDirectory:
    """The provider for account review. Authentik raises here if its integration is unconfigured."""
    state = request.app.state
    return build_account_directory(state.settings, state.oidc_http, state.session_factory)


def optional_account_directory(request: Request) -> AccountDirectory | None:
    """As above, but ``None`` when Authentik's review integration is not configured."""
    settings: Settings = request.app.state.settings
    if not _is_local(settings) and not (
        settings.authentik_review_url and settings.authentik_review_token
    ):
        return None
    return account_directory(request)


def administrator_directory(request: Request) -> AdministratorDirectory:
    state = request.app.state
    if _is_local(state.settings):
        from identity.local_auth.adapters import LocalAdministratorProvider
        from identity.local_auth.http import local_auth

        return LocalAdministratorProvider(state.session_factory, local_auth(request))
    from identity.services.administrator_provider import AdministratorProvider

    return AdministratorProvider(state.settings, state.oidc_http)


def recovery_supported(settings: Settings, subject: str | uuid.UUID) -> bool:
    """Whether this subject belongs to an account the active provider can recover."""
    if _is_local(settings):
        from identity.local_auth.adapters import LocalRecoveryProvider

        return LocalRecoveryProvider.subject_field(subject) is not None
    from identity.services.administrator_recovery import AdministratorRecoveryProvider

    return AdministratorRecoveryProvider.subject_field(subject) is not None


def recovery_directory(request: Request) -> RecoveryDirectory:
    state = request.app.state
    if _is_local(state.settings):
        from identity.local_auth.adapters import LocalRecoveryProvider
        from identity.local_auth.http import local_auth

        return LocalRecoveryProvider(state.session_factory, local_auth(request))
    from identity.services.administrator_recovery import AdministratorRecoveryProvider

    return AdministratorRecoveryProvider(state.settings, state.oidc_http)
