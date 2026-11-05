from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.errors import ConflictError

from identity.config import Settings
from identity.services.administrator_provider import (
    AdministratorProvider,
    AdministratorProviderUnavailableError,
)


def settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret="a" * 32,
        cursor_signing_secret="b" * 32,
        authentik_provision_url="https://authentik.test",
        authentik_provision_token="c" * 32,
    )


@pytest.mark.asyncio
async def test_create_reconciles_provider_retry_without_leaking_password():
    marker = uuid.uuid4()
    username = AdministratorProvider.username_for("owner@example.test")
    row = {
        "pk": 42,
        "uid": "f" * 64,
        "username": username,
        "email": "owner@example.test",
        "name": "Owner",
        "path": "bill/tenant-administrators",
        "type": "external",
        "is_active": False,
        "is_superuser": False,
        "groups": [],
        "roles": [],
        "attributes": {
            "billing_email_verified": True,
            "billing_tenant_provision_command": str(marker),
        },
    }
    calls = []

    def send(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"results": [] if len(calls) == 1 else [row], "pagination": {"next": 0}}
            )
        if request.url.path.endswith("/set_password/"):
            return httpx.Response(204)
        return httpx.Response(201, json=row)

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http:
        provider = AdministratorProvider(settings(), http)
        first = await provider.create(
            email="owner@example.test",
            name="Owner",
            password="temporary-password-123",
            marker=marker,
        )
        second = await provider.create(
            email="owner@example.test",
            name="Owner",
            password="temporary-password-123",
            marker=marker,
        )
    assert first == second == (username, "f" * 64)
    assert [request.method for request in calls] == ["GET", "POST", "POST", "GET", "POST"]
    assert all("temporary-password-123" not in str(request.url) for request in calls)


@pytest.mark.asyncio
async def test_rejects_duplicate_or_unverified_existing_account():
    row = {
        "pk": 2,
        "uid": "f" * 64,
        "email": "owner@example.test",
        "type": "external",
        "is_active": True,
        "is_superuser": False,
        "groups": [],
        "roles": [],
        "attributes": {"billing_email_verified": False},
    }
    with pytest.raises(ConflictError):
        AdministratorProvider.confirm(row, "owner@example.test")

    async def send(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http:
        with pytest.raises(AdministratorProviderUnavailableError):
            await AdministratorProvider(settings(), http).by_email("owner@example.test")


@pytest.mark.asyncio
async def test_activation_requires_exact_command_marker_and_readback():
    marker = uuid.uuid4()
    row = {
        "pk": 42,
        "uid": "f" * 64,
        "username": AdministratorProvider.username_for("owner@example.test"),
        "email": "owner@example.test",
        "name": "Owner",
        "path": "bill/tenant-administrators",
        "type": "external",
        "is_active": False,
        "is_superuser": False,
        "groups": [],
        "roles": [],
        "attributes": {
            "billing_email_verified": True,
            "billing_tenant_provision_command": str(marker),
        },
    }
    methods = []

    def send(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "PATCH":
            row["is_active"] = True
            return httpx.Response(200, json=row)
        return httpx.Response(
            200,
            json=row
            if request.url.path.endswith("/42/")
            else {"results": [row], "pagination": {"next": 0}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http:
        provider = AdministratorProvider(settings(), http)
        await provider.activate(email=row["email"], marker=marker, subject=row["uid"])
    assert methods == ["GET", "PATCH", "GET"]
    assert row["is_active"] is True


@pytest.mark.asyncio
async def test_replay_does_not_reset_an_active_administrator_password(monkeypatch):
    marker = uuid.uuid4()
    email = "owner@example.test"
    row = {
        "pk": 42,
        "uid": "f" * 64,
        "username": AdministratorProvider.username_for(email),
        "email": email,
        "name": "Owner",
        "path": "bill/tenant-administrators",
        "type": "external",
        "is_active": True,
        "is_superuser": False,
        "groups": [],
        "roles": [],
        "attributes": {
            "billing_email_verified": True,
            "billing_tenant_provision_command": str(marker),
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    ) as http:
        provider = AdministratorProvider(settings(), http)

        async def by_email(value):
            assert value == email
            return row

        monkeypatch.setattr(provider, "by_email", by_email)
        assert await provider.create(
            email=email, name="Owner", password="changed-password", marker=marker
        ) == (row["username"], row["uid"])
