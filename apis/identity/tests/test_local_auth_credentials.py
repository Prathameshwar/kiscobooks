"""Sign-in, sign-up, password change, recovery and first-administrator setup.

See docs/local-auth.md §4 and §6.

Failure modes named here: an account that can be told apart by its error, a lockout that is rolled
back with the failed request, a recovery link that works twice, a password change that leaves old
sessions alive, a setup endpoint that opens after setup closed.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from identity.local_auth import domain, offload
from identity.models import Outbox, Tenant, User
from identity.models.local_auth import (
    PATH_ADMINISTRATORS,
    PATH_PENDING,
    PATH_PLATFORM,
    LocalAuthorization,
    LocalCredential,
    LocalIdentity,
    LocalRecoveryToken,
    LocalRefreshToken,
)
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_platform_installation,
    build_role,
    build_role_assignment,
    build_role_permission,
    build_tenant,
    build_user,
)
from tests.local_auth_support import (
    BFF,
    PASSWORD,
    UI,
    begin,
    decode_unverified,
    light_engine,
    redeem,
    refresh,
    sign_in,
    tokens,
)

EMAIL = "asha@alpha.example"
LOGIN = "/internal/v1/local-auth/login"
REGISTER = "/internal/v1/local-auth/registrations"
NEW_PASSWORD = "a brand new passphrase"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = await light_engine(enforce_foreign_keys=False)
    yield eng
    await eng.dispose()


async def make_identity(
    app: Any,
    factory: async_sessionmaker[AsyncSession],
    *,
    email: str = EMAIL,
    username: str = "asha",
    password: str = PASSWORD,
    status: str = "active",
    path: str = PATH_ADMINISTRATORS,
    verified: bool = True,
) -> LocalIdentity:
    async with factory() as db:
        identity = await app.state.local_auth.create_account(
            db,
            name="Asha Rao",
            username=username,
            email=email,
            password=password,
            region=("IN", "IN-KA"),
            workspace_name=None,
            path=path,
            status=status,
            verified=verified,
        )
        await db.commit()
        return identity


@pytest_asyncio.fixture
async def account(local_app: Any, factory: async_sessionmaker[AsyncSession]) -> LocalIdentity:
    return await make_identity(local_app, factory)


async def attach_user(
    factory: async_sessionmaker[AsyncSession],
    identity: LocalIdentity,
    *,
    tenant_id: uuid.UUID | None = None,
    email: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A tenant and an active user whose subject is the identity's."""
    tenant = build_tenant(tenant_id=tenant_id, slug=f"t{uuid.uuid4().hex[:8]}")
    user = build_user(
        tenant_id=tenant.id,
        email=email or identity.email,
        authentik_sub=identity.sub,
        user_type="tenant_admin",
    )
    async with factory() as db:
        db.add(tenant)
        await db.flush()
        db.add(user)
        await db.commit()
    return tenant.id, user.id


def plain(response: httpx.Response) -> dict[str, Any]:
    """The body without the per-request trace id, so two answers can be compared."""
    body: dict[str, Any] = response.json()
    body["error"].pop("trace_id", None)
    return body


async def login(
    client: httpx.AsyncClient, request_id: str, email: str, password: str, **headers: str
) -> httpx.Response:
    return await client.post(
        LOGIN,
        json={"request_id": request_id, "email": email, "password": password},
        headers={**BFF, **headers},
    )


async def events(factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> list[str]:
    async with factory() as db:
        rows = await db.scalars(select(Outbox).where(Outbox.tenant_id == tenant_id))
        return sorted(row.event_type for row in rows)


@pytest.fixture
def signed(local_app: Any) -> Iterator[Any]:
    """Header-signed actors instead of bearer tokens, for routes a person calls with a session."""
    verifier = local_app.state.token_verifier
    local_app.state.token_verifier = None
    yield local_app
    local_app.state.token_verifier = verifier


# --------------------------------------------------------------------------- the BFF boundary


class TestBffBoundary:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/internal/v1/local-auth/status"),
            ("GET", "/internal/v1/local-auth/requests/" + "a" * 43),
            ("POST", LOGIN),
            ("POST", REGISTER),
            ("POST", "/internal/v1/local-auth/password/recovery/inspect"),
            ("POST", "/internal/v1/local-auth/password/recovery/redeem"),
            ("POST", "/internal/v1/local-auth/setup/administrator"),
        ],
    )
    @pytest.mark.parametrize(
        "headers", [{}, {"X-Auth-Bff-Secret": "wrong" * 8}, {"X-Auth-Bff-Secret": ""}]
    )
    async def test_only_the_auth_app_may_call_these(
        self, local_client: httpx.AsyncClient, method: str, path: str, headers: dict[str, str]
    ) -> None:
        response = await local_client.request(
            method, path, headers=headers, json={} if method == "POST" else None
        )
        assert response.status_code == 401, (method, path, response.text)

    async def test_status_says_what_the_auth_app_needs_to_know(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        body = (await local_client.get("/internal/v1/local-auth/status", headers=BFF)).json()
        assert body == {
            "provider": "local",
            "registration_enabled": True,
            "recovery": {"link": True, "email": False},
            "setup": {"administrator_exists": False},
        }

    async def test_the_request_endpoint_reports_a_live_request_and_hides_a_dead_one(
        self, local_client: httpx.AsyncClient
    ) -> None:
        request_id = await begin(local_client)
        live = await local_client.get(f"/internal/v1/local-auth/requests/{request_id}", headers=BFF)
        assert live.status_code == 200 and "expires_at" in live.json()
        dead = await local_client.get("/internal/v1/local-auth/requests/" + "z" * 43, headers=BFF)
        assert (
            dead.status_code == 404
            and dead.json()["error"]["code"] == "authorization_request_invalid"
        )

    async def test_a_body_with_an_unknown_field_is_refused(
        self, local_client: httpx.AsyncClient
    ) -> None:
        request_id = await begin(local_client)
        response = await local_client.post(
            LOGIN,
            json={"request_id": request_id, "email": EMAIL, "password": PASSWORD, "role": "admin"},
            headers=BFF,
        )
        assert response.status_code == 422


# --------------------------------------------------------------------------- sign-in


class TestSignIn:
    async def test_login_rejects_ambiguous_identifier_fields(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        response = await local_client.post(
            LOGIN,
            json={
                "request_id": await begin(local_client),
                "identifier": account.username,
                "email": account.email,
                "password": PASSWORD,
            },
            headers=BFF,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("identifier", ["nobody", "nobody@alpha.example"])
    async def test_unknown_identifiers_and_wrong_passwords_have_the_same_answer(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        identifier: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        spent: list[str] = []
        monkeypatch.setattr(domain, "burn_verification", lambda password: spent.append(password))
        unknown = await login(local_client, await begin(local_client), identifier, PASSWORD)
        wrong = await login(local_client, await begin(local_client), account.username, "wrong")
        assert unknown.status_code == wrong.status_code == 401
        assert plain(unknown) == plain(wrong)
        assert spent == [PASSWORD]

    @pytest.mark.parametrize("status", ["pending", "disabled"])
    async def test_username_obeys_account_status_after_password_verification(
        self,
        local_client: httpx.AsyncClient,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        status: str,
    ) -> None:
        identity = await make_identity(local_app, factory, status=status)
        wrong = await login(local_client, await begin(local_client), identity.username, "wrong")
        right = await login(local_client, await begin(local_client), identity.username, PASSWORD)
        assert wrong.status_code == 401
        assert right.status_code == 403
        assert right.json()["error"]["code"] == f"account_{status}"

    async def test_provisioned_administrator_can_sign_in_by_username(
        self,
        local_client: httpx.AsyncClient,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        identity = await make_identity(local_app, factory, username="bill-admin-" + "a" * 32)
        assert (
            await login(local_client, await begin(local_client), identity.username, PASSWORD)
        ).status_code == 200

    @pytest.mark.parametrize("identifier", ["asha", "  ASHA  ", EMAIL, " ASHA@Alpha.Example "])
    async def test_username_or_email_signs_in_as_the_same_identity(
        self, local_client: httpx.AsyncClient, account: LocalIdentity, identifier: str
    ) -> None:
        response = await local_client.post(
            LOGIN,
            json={
                "request_id": await begin(local_client),
                "identifier": identifier,
                "password": PASSWORD,
            },
            headers=BFF,
        )
        assert response.status_code == 200, response.text
        code = parse_qs(urlsplit(response.json()["redirect_to"]).query)["code"][0]
        result = await redeem(local_client, code)
        assert result.status_code == 200
        assert decode_unverified(result.json()["id_token"])["sub"] == account.sub

    async def test_switching_identifiers_cannot_bypass_lockout(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        for identifier in (account.username, account.email, account.username.upper()):
            response = await login(local_client, await begin(local_client), identifier, "wrong")
            assert response.status_code == 401
        for identifier in (account.username, account.email):
            response = await login(local_client, await begin(local_client), identifier, PASSWORD)
            assert response.status_code == 423

    async def test_both_identifiers_share_the_account_rate_limit(
        self, local_client: httpx.AsyncClient, account: LocalIdentity, local_app: Any
    ) -> None:
        local_app.state.local_limiter.clock = lambda: 120.0
        for index in range(10):
            identifier = account.username if index % 2 else account.email
            assert (
                await login(local_client, await begin(local_client), identifier, PASSWORD)
            ).status_code == 200
        assert (
            await login(local_client, await begin(local_client), account.username, PASSWORD)
        ).status_code == 429

    async def test_the_right_password_returns_the_callback_with_a_code_and_the_state(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        response = await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        assert response.status_code == 200
        target = response.json()["redirect_to"]
        assert target.startswith("http://localhost:4310/api/auth/callback/local?")
        assert "code=" in target and "state=state-123" in target
        assert PASSWORD not in response.text

    async def test_email_is_matched_ignoring_case_and_surrounding_space(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        response = await login(
            local_client, await begin(local_client), "  ASHA@Alpha.Example ", PASSWORD
        )
        assert response.status_code == 200

    async def test_an_unknown_email_and_a_wrong_password_are_the_same_answer(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        unknown = await login(
            local_client, await begin(local_client), "nobody@alpha.example", PASSWORD
        )
        wrong = await login(local_client, await begin(local_client), EMAIL, "not the password")
        assert unknown.status_code == wrong.status_code == 401
        assert plain(unknown) == plain(wrong)
        assert unknown.json()["error"]["code"] == "invalid_credentials"

    async def test_an_unknown_email_still_costs_a_password_check(
        self, local_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spent: list[str] = []
        monkeypatch.setattr(domain, "burn_verification", lambda password: spent.append(password))
        await login(local_client, await begin(local_client), "nobody@alpha.example", "x" * 8)
        assert spent == ["x" * 8]

    @pytest.mark.parametrize("email", ["", "no-at-sign", "a@b", "x" * 400 + "@a.bc"])
    async def test_a_malformed_email_is_just_wrong_credentials(
        self, local_client: httpx.AsyncClient, email: str
    ) -> None:
        response = await login(local_client, await begin(local_client), email or "a@b", PASSWORD)
        assert response.status_code in (401, 422)

    async def test_a_pending_account_is_told_so_only_after_the_password_is_right(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await make_identity(local_app, factory, status="pending", path=PATH_PENDING, verified=False)
        wrong = await login(local_client, await begin(local_client), EMAIL, "wrong password")
        right = await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        assert wrong.status_code == 401
        assert right.status_code == 403 and right.json()["error"]["code"] == "account_pending"

    async def test_a_disabled_account_cannot_sign_in(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await make_identity(local_app, factory, status="disabled")
        response = await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        assert (
            response.status_code == 403 and response.json()["error"]["code"] == "account_disabled"
        )

    async def test_a_request_is_single_use(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        request_id = await begin(local_client)
        assert (await login(local_client, request_id, EMAIL, PASSWORD)).status_code == 200
        again = await login(local_client, request_id, EMAIL, PASSWORD)
        assert (
            again.status_code == 404
            and again.json()["error"]["code"] == "authorization_request_invalid"
        )

    async def test_an_expired_request_is_refused(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        request_id = await begin(local_client)
        async with factory() as db:
            await db.execute(
                update(LocalAuthorization).values(expires_at=utcnow() - dt.timedelta(seconds=1))
            )
            await db.commit()
        assert (await login(local_client, request_id, EMAIL, PASSWORD)).status_code == 404

    async def test_a_stronger_hash_setting_upgrades_the_stored_hash_at_sign_in(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with factory() as db:
            before = (await db.get(LocalCredential, account.seq)).password_hash  # type: ignore[union-attr]
        domain.configure_hashing(domain.HashParameters(time_cost=2, memory_kib=16, parallelism=1))
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 200
        async with factory() as db:
            after = (await db.get(LocalCredential, account.seq)).password_hash  # type: ignore[union-attr]
        assert after != before and "t=2" in after
        assert domain.verify_password(after, PASSWORD)

    async def test_hashing_runs_off_the_event_loop(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A slow hash must not stop the worker answering anything else (rule 4.10)."""
        request_id = await begin(local_client)

        def slow(stored: str, password: str) -> bool:
            time.sleep(0.4)
            return False

        monkeypatch.setattr(domain, "verify_password", slow)
        beats: list[float] = [time.perf_counter()]

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(0.01)
                beats.append(time.perf_counter())

        beat = asyncio.create_task(heartbeat())
        try:
            response = await login(local_client, request_id, EMAIL, "not the password")
        finally:
            beat.cancel()
        assert response.status_code == 401
        # Inline, the loop stands still for the whole 0.4 s hash: one gap that long between beats.
        longest = max(later - earlier for earlier, later in pairwise(beats))
        assert longest < 0.25, f"the event loop was blocked for {longest:.2f}s"

    async def test_a_flood_of_hashing_is_refused_not_queued_without_bound(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        request_id = await begin(local_client)
        monkeypatch.setattr(offload, "_waiting", offload.WORKERS + offload.QUEUE_LIMIT)
        response = await login(local_client, request_id, EMAIL, PASSWORD)
        assert response.status_code == 429
        # The refusal is not a verdict on the password: nothing was counted against the account.
        async with factory() as db:
            credential = (await db.scalars(select(LocalCredential))).one()
        assert credential.failed_attempts == 0


class TestLockout:
    async def test_failures_lock_the_account_and_the_lock_survives_the_failed_requests(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        for _ in range(3):  # the settings allow three
            assert (
                await login(local_client, await begin(local_client), EMAIL, "nope nope")
            ).status_code == 401
        locked = await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        assert locked.status_code == 423
        body = locked.json()
        assert body["error"]["code"] == "account_locked" and 0 < body["retry_after"] <= 900
        assert locked.headers["retry-after"] == str(body["retry_after"])
        async with factory() as db:
            credential = await db.get(LocalCredential, account.seq)
        assert credential is not None and credential.lock_ends_at is not None

    async def test_the_right_password_does_not_get_through_a_lock(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        for _ in range(3):
            await login(local_client, await begin(local_client), EMAIL, "nope nope")
        for _ in range(2):
            assert (
                await login(local_client, await begin(local_client), EMAIL, PASSWORD)
            ).status_code == 423

    async def test_a_lock_releases_after_its_time_and_a_success_clears_the_count(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        for _ in range(3):
            await login(local_client, await begin(local_client), EMAIL, "nope nope")
        async with factory() as db:
            await db.execute(
                update(LocalCredential).values(lock_ends_at=utcnow() - dt.timedelta(seconds=1))
            )
            await db.commit()
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 200
        async with factory() as db:
            credential = await db.get(LocalCredential, account.seq)
        assert (
            credential is not None
            and credential.failed_attempts == 0
            and credential.lock_ends_at is None
        )

    async def test_two_failures_then_a_success_start_the_count_again(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        for _ in range(2):
            await login(local_client, await begin(local_client), EMAIL, "nope nope")
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 200
        for _ in range(2):
            assert (
                await login(local_client, await begin(local_client), EMAIL, "nope nope")
            ).status_code == 401
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 200

    async def test_a_lock_on_one_account_does_not_touch_another(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await make_identity(local_app, factory, email="ravi@alpha.example", username="ravi")
        for _ in range(3):
            await login(local_client, await begin(local_client), EMAIL, "nope nope")
        assert (
            await login(local_client, await begin(local_client), "ravi@alpha.example", PASSWORD)
        ).status_code == 200

    async def test_the_per_account_throttle_answers_429_before_it_does_any_work(
        self, local_client: httpx.AsyncClient
    ) -> None:
        statuses = [
            (
                await login(
                    local_client, await begin(local_client), "someone@alpha.example", "wrong one"
                )
            ).status_code
            for _ in range(12)
        ]
        assert statuses.count(429) >= 1 and statuses[0] == 401

    async def test_without_a_forwarded_address_there_is_no_shared_per_address_limit(
        self, local_client: httpx.AsyncClient
    ) -> None:
        # Every call comes from the Auth app; a window on that address would cap the whole
        # installation, not an attacker. Distinct accounts must each get their own budget.
        statuses = [
            (
                await login(local_client, await begin(local_client), f"p{i}@alpha.example", "x" * 8)
            ).status_code
            for i in range(65)
        ]
        assert set(statuses) == {401}

    async def test_a_forwarded_client_address_is_what_is_throttled(
        self, local_client: httpx.AsyncClient, local_app: Any
    ) -> None:
        # The Auth app is one connection to Identity; the throttle must see the person behind it.
        # Keep all attempts in one rate window even when the real clock crosses a minute.
        clock = [120.0]
        local_app.state.local_limiter.clock = lambda: clock[0]
        statuses = [
            (
                await login(
                    local_client,
                    await begin(local_client),
                    f"p{i}@alpha.example",
                    "x" * 8,
                    **{"X-Client-Address": "203.0.113.9"},
                )
            ).status_code
            for i in range(65)
        ]
        assert statuses[-1] == 429 and statuses[0] == 401
        other_address = await login(
            local_client,
            await begin(local_client),
            "different@alpha.example",
            "x" * 8,
            **{"X-Client-Address": "203.0.113.10"},
        )
        assert other_address.status_code == 401
        clock[0] += 60
        next_window = await login(
            local_client,
            await begin(local_client),
            "next-window@alpha.example",
            "x" * 8,
            **{"X-Client-Address": "203.0.113.9"},
        )
        assert next_window.status_code == 401

    async def test_every_spelling_the_database_treats_as_one_account_shares_one_throttle(
        self, local_client: httpx.AsyncClient
    ) -> None:
        # The email column is accent- and case-insensitive, so these are one account to MySQL.
        spellings = ["nobody@alpha.example", "NOBODY@alpha.example", "nóbody@alpha.example"]
        statuses = []
        for attempt in range(12):
            request_id = await begin(local_client)
            statuses.append(
                (
                    await login(local_client, request_id, spellings[attempt % 3], "whatever 12")
                ).status_code
            )
        assert statuses[:10] == [401] * 10
        assert statuses[10:] == [429, 429]


class TestAudit:
    async def test_sign_in_and_lockout_are_recorded_against_the_linked_user(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant_id, _ = await attach_user(factory, account)
        await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        for _ in range(3):
            await login(local_client, await begin(local_client), EMAIL, "nope nope")
        recorded = await events(factory, tenant_id)
        assert recorded.count("user.sign_in") == 1 and recorded.count("user.account_locked") == 1

    async def test_an_unlinked_sign_up_leaves_no_audit_row_and_no_password_in_any_event(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        async with factory() as db:
            assert list(await db.scalars(select(Outbox))) == []


# --------------------------------------------------------------------------- sign-up


def registration(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "Ravi Menon",
        "username": "ravi.menon",
        "email": "Ravi@Beta.example",
        "password": PASSWORD,
        "country_code": "IN",
        "state_code": "IN-KA",
        "workspace_name": "Ravi Books",
    }
    return body | overrides


class TestRegistration:
    async def test_a_sign_up_is_created_pending_unverified_and_hashed(
        self, local_client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        response = await local_client.post(REGISTER, json=registration(), headers=BFF)
        assert response.status_code == 201 and response.json() == {"status": "pending-review"}
        async with factory() as db:
            identity = (await db.scalars(select(LocalIdentity))).one()
            credential = await db.get(LocalCredential, identity.seq)
        assert identity.email == "ravi@beta.example" and identity.username == "ravi.menon"
        assert identity.status == "pending" and identity.path == PATH_PENDING
        assert identity.email_verified_at is None and identity.workspace_name == "Ravi Books"
        assert len(identity.sub) == 64 and identity.sub != identity.email
        assert credential is not None and credential.password_hash.startswith("$argon2id$")

    async def test_a_new_sign_up_cannot_sign_in_until_approved(
        self, local_client: httpx.AsyncClient
    ) -> None:
        await local_client.post(REGISTER, json=registration(), headers=BFF)
        response = await login(
            local_client, await begin(local_client), "ravi@beta.example", PASSWORD
        )
        assert response.status_code == 403 and response.json()["error"]["code"] == "account_pending"

    async def test_a_taken_email_or_username_is_the_same_generic_refusal(
        self, local_app: Any, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        email_taken = await local_client.post(REGISTER, json=registration(email=EMAIL), headers=BFF)
        name_taken = await local_client.post(
            REGISTER, json=registration(username="asha"), headers=BFF
        )
        assert email_taken.status_code == name_taken.status_code == 422
        assert plain(email_taken) == plain(name_taken)
        assert email_taken.json()["error"]["code"] == "registration_unavailable"
        assert "fields" not in email_taken.json()["error"]
        # And the real account is untouched.
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 200

    async def test_an_email_that_differs_only_by_case_is_taken(
        self, local_client: httpx.AsyncClient, account: LocalIdentity
    ) -> None:
        response = await local_client.post(
            REGISTER, json=registration(email="ASHA@ALPHA.EXAMPLE"), headers=BFF
        )
        assert (
            response.status_code == 422
            and response.json()["error"]["code"] == "registration_unavailable"
        )

    @pytest.mark.parametrize(
        ("override", "field"),
        [
            ({"name": "  "}, "name"),
            ({"name": "x" * 101}, "name"),
            ({"username": "Ab"}, "username"),
            ({"username": "-bad"}, "username"),
            ({"email": "nope"}, "email"),
            ({"password": "12345"}, "password"),
            ({"password": "a" * 129}, "password"),
            ({"password": "tab\there"}, "password"),
            ({"country_code": "india"}, "country_code"),
            ({"state_code": "KA"}, "country_code"),
            ({"workspace_name": "x" * 201}, "workspace_name"),
        ],
    )
    async def test_invalid_fields_are_named(
        self, local_client: httpx.AsyncClient, override: dict[str, object], field: str
    ) -> None:
        response = await local_client.post(REGISTER, json=registration(**override), headers=BFF)
        assert response.status_code == 422
        assert field in response.json()["error"]["fields"], response.text

    async def test_the_password_limits_are_inclusive(self, local_client: httpx.AsyncClient) -> None:
        low = await local_client.post(REGISTER, json=registration(password="a" * 6), headers=BFF)
        high = await local_client.post(
            REGISTER,
            json=registration(password="b" * 128, email="x@y.example", username="other"),
            headers=BFF,
        )
        assert low.status_code == high.status_code == 201

    async def test_extra_or_privileged_fields_are_refused(
        self, local_client: httpx.AsyncClient
    ) -> None:
        for extra in (
            {"status": "active"},
            {"path": "bill/platform-administrator"},
            {"is_superuser": True},
        ):
            response = await local_client.post(REGISTER, json=registration(**extra), headers=BFF)
            assert response.status_code == 422

    async def test_registration_can_be_switched_off(
        self, local_app: Any, local_client: httpx.AsyncClient
    ) -> None:
        from identity.config import LocalAuthSettings
        from identity.local_auth.service import LocalAuth
        from tests.local_auth_support import local_settings

        settings: LocalAuthSettings = local_settings(registration_enabled=False)
        local_app.state.local_auth = LocalAuth(settings)
        response = await local_client.post(REGISTER, json=registration(), headers=BFF)
        assert (
            response.status_code == 422
            and response.json()["error"]["code"] == "registration_unavailable"
        )

    async def test_a_sign_up_never_lands_in_an_administrator_path_or_active(
        self, local_client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await local_client.post(REGISTER, json=registration(), headers=BFF)
        async with factory() as db:
            identity = (await db.scalars(select(LocalIdentity))).one()
        assert identity.path != PATH_PLATFORM and identity.path != PATH_ADMINISTRATORS
        assert identity.status == "pending"

    # --------------------------------------------------------------------------- password change

    @pytest.mark.parametrize(
        "username",
        ["bill-admin-" + "0123456789abcdef" * 2, "admin-" + "f" * 32, "BILL-ADMIN-" + "a" * 32],
    )
    async def test_the_names_the_platform_derives_for_provisioned_accounts_cannot_be_taken(
        self, local_client: httpx.AsyncClient, username: str
    ) -> None:
        response = await local_client.post(
            REGISTER, json=registration(username=username), headers=BFF
        )
        assert response.status_code == 422
        assert "username" in response.json()["error"]["fields"]


class TestPasswordChange:
    PATH = "/v1/session/password"

    async def headers(
        self, factory: async_sessionmaker[AsyncSession], identity: LocalIdentity
    ) -> dict[str, str]:
        tenant_id, user_id = await attach_user(factory, identity)
        return actor_headers(tenant_id=tenant_id, user_id=user_id, grants=[grant(["user.read"])])

    async def test_changing_it_works_ends_old_sessions_and_the_new_one_signs_in(
        self,
        signed: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        first = await tokens(local_client, EMAIL)
        headers = await self.headers(factory, account)
        response = await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers,
        )
        assert response.status_code == 204 and response.headers["cache-control"] == "no-store"
        # Every session the old password made is over, at the refresh token and at the user row.
        assert (await refresh(local_client, first["refresh_token"])).status_code == 400
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 401
        assert (
            await login(local_client, await begin(local_client), EMAIL, NEW_PASSWORD)
        ).status_code == 200
        with unfiltered():
            async with factory() as db:
                user = (await db.scalars(select(User))).one()
        assert user.tokens_valid_after_at is not None

    async def test_a_sign_in_in_the_same_second_as_the_change_is_not_refused_by_the_verifier(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        verifier = local_app.state.token_verifier
        local_app.state.token_verifier = None
        headers = await self.headers(factory, account)
        old = await tokens(local_client, EMAIL)
        await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers,
        )
        local_app.state.token_verifier = verifier
        fresh = await tokens(local_client, EMAIL, NEW_PASSWORD)

        def bearer(token: str) -> dict[str, str]:
            return {"Authorization": f"Bearer {token}"}

        # The API's own revocation check (api/auth.py) compares whole seconds with a fractional
        # revocation time: a sign-in in the change's own second is accepted, the old session is not.
        accepted = await local_client.get("/v1/session", headers=bearer(fresh["access_token"]))
        assert accepted.status_code == 200
        refused = await local_client.get("/v1/session", headers=bearer(old["access_token"]))
        assert refused.status_code == 401

    async def test_a_code_obtained_before_the_change_cannot_be_redeemed_after_it(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Else a thief who signed in with the old password keeps the session the owner ended."""
        await attach_user(factory, account)
        code = await sign_in(local_client, EMAIL)
        async with factory() as db:
            await local_app.state.local_auth.change_password(
                db, account.sub, PASSWORD, NEW_PASSWORD
            )
            await db.commit()
        response = await redeem(local_client, code)
        assert response.status_code == 400 and response.json()["error"] == "invalid_grant"
        async with factory() as db:
            assert list(await db.scalars(select(LocalRefreshToken))) == []

    async def test_changing_the_password_voids_a_recovery_link_that_was_still_open(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await attach_user(factory, account)
        async with factory() as db:
            token, _ = await local_app.state.local_auth.issue_recovery(db, account, issued_by=None)
            await db.commit()
        async with factory() as db:
            await local_app.state.local_auth.change_password(
                db, account.sub, PASSWORD, NEW_PASSWORD
            )
            await db.commit()
        redeemed = await local_client.post(
            "/internal/v1/local-auth/password/recovery/redeem",
            json={"token": token, "new_password": "somebody else chose this"},
            headers=BFF,
        )
        assert redeemed.status_code == 404

    async def test_an_api_token_cannot_be_used_to_change_or_guess_a_password(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant, user = await attach_user(factory, account)
        async with factory() as db:
            role = build_role(tenant_id=tenant, key="reader")
            db.add(role)
            await db.flush()
            db.add(
                build_role_permission(tenant_id=tenant, role_id=role.id, permission_key="user.read")
            )
            db.add(build_role_assignment(tenant_id=tenant, role_id=role.id, subject_id=user))
            await db.commit()
        session = {"Authorization": f"Bearer {(await tokens(local_client, EMAIL))['access_token']}"}
        created = await local_client.post(
            "/v1/session/api-tokens",
            headers=session,
            json={"name": "Reporting", "permissions": ["user.read"]},
        )
        assert created.status_code == 201, created.text
        automation = {"Authorization": f"Bearer {created.json()['token']}"}
        refused = await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=automation,
        )
        assert refused.status_code == 403
        # The password was not changed, and the same call from the person's own session works.
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 200
        allowed = await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=session,
        )
        assert allowed.status_code == 204, allowed.text

    async def test_the_current_password_must_be_right_and_wrong_guesses_count_toward_the_lock(
        self,
        signed: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        headers = await self.headers(factory, account)
        for _ in range(2):
            wrong = await local_client.post(
                self.PATH,
                json={"current_password": "not it", "new_password": NEW_PASSWORD},
                headers=headers,
            )
            assert (
                wrong.status_code == 422 and "current_password" in wrong.json()["error"]["fields"]
            )
        await local_client.post(
            self.PATH,
            json={"current_password": "not it", "new_password": NEW_PASSWORD},
            headers=headers,
        )
        locked = await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers,
        )
        assert locked.status_code == 423 and locked.json()["retry_after"] > 0
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 423

    @pytest.mark.parametrize("new", ["short", "a" * 129, "tab\tinside"])
    async def test_a_weak_new_password_is_refused_and_nothing_changes(
        self,
        signed: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
        new: str,
    ) -> None:
        headers = await self.headers(factory, account)
        response = await local_client.post(
            self.PATH, json={"current_password": PASSWORD, "new_password": new}, headers=headers
        )
        assert response.status_code == 422 and "new_password" in response.json()["error"]["fields"]
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 200

    async def test_reusing_the_current_password_is_refused(
        self,
        signed: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        headers = await self.headers(factory, account)
        response = await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": PASSWORD},
            headers=headers,
        )
        assert response.status_code == 422 and "new_password" in response.json()["error"]["fields"]

    async def test_it_needs_a_session(self, signed: Any, local_client: httpx.AsyncClient) -> None:
        response = await local_client.post(
            self.PATH, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        )
        assert response.status_code == 401

    async def test_a_user_with_no_local_password_gets_a_clear_conflict(
        self,
        signed: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = build_tenant(slug="solo")
        user = build_user(tenant_id=tenant.id, email="solo@alpha.example")
        async with factory() as db:
            db.add(tenant)
            await db.flush()
            db.add(user)
            await db.commit()
        response = await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=actor_headers(tenant_id=tenant.id, user_id=user.id),
        )
        assert response.status_code == 409

    async def test_under_authentik_the_provider_owns_passwords(
        self, client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        response = await client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=actor_headers(tenant_id=uuid.uuid4(), user_id=uuid.uuid4()),
        )
        assert response.status_code == 409

    async def test_the_change_is_audited_without_the_password(
        self,
        signed: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        headers = await self.headers(factory, account)
        await local_client.post(
            self.PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers,
        )
        async with factory() as db:
            rows = list(
                await db.scalars(select(Outbox).where(Outbox.event_type == "user.password_changed"))
            )
        assert len(rows) == 1
        assert PASSWORD not in str(rows[0].payload) and NEW_PASSWORD not in str(rows[0].payload)


# --------------------------------------------------------------------------- recovery


class TestRecovery:
    INSPECT = "/internal/v1/local-auth/password/recovery/inspect"
    REDEEM = "/internal/v1/local-auth/password/recovery/redeem"

    async def issue(
        self, app: Any, factory: async_sessionmaker[AsyncSession], identity: LocalIdentity
    ) -> str:
        async with factory() as db:
            row = await db.get(LocalIdentity, identity.seq)
            assert row is not None
            token, _ = await app.state.local_auth.issue_recovery(db, row, issued_by=None)
            await db.commit()
        return token

    async def test_a_live_link_inspects_and_redeems_once(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        token = await self.issue(local_app, factory, account)
        assert (
            await local_client.post(self.INSPECT, json={"token": token}, headers=BFF)
        ).json() == {"valid": True}
        redeemed = await local_client.post(
            self.REDEEM, json={"token": token, "new_password": NEW_PASSWORD}, headers=BFF
        )
        assert redeemed.status_code == 204
        assert (
            await login(local_client, await begin(local_client), EMAIL, NEW_PASSWORD)
        ).status_code == 200
        assert (
            await login(local_client, await begin(local_client), EMAIL, PASSWORD)
        ).status_code == 401
        again = await local_client.post(
            self.REDEEM, json={"token": token, "new_password": "another one!"}, headers=BFF
        )
        assert again.status_code == 404 and again.json()["error"]["code"] == "recovery_invalid"
        assert (
            await local_client.post(self.INSPECT, json={"token": token}, headers=BFF)
        ).status_code == 404

    async def test_redeeming_ends_every_session_and_clears_a_lock(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        first = await tokens(local_client, EMAIL)
        for _ in range(3):
            await login(local_client, await begin(local_client), EMAIL, "nope nope")
        token = await self.issue(local_app, factory, account)
        await local_client.post(
            self.REDEEM, json={"token": token, "new_password": NEW_PASSWORD}, headers=BFF
        )
        assert (await refresh(local_client, first["refresh_token"])).status_code == 400
        assert (
            await login(local_client, await begin(local_client), EMAIL, NEW_PASSWORD)
        ).status_code == 200

    async def test_a_weak_password_is_refused_and_the_link_stays_usable(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        token = await self.issue(local_app, factory, account)
        weak = await local_client.post(
            self.REDEEM, json={"token": token, "new_password": "short"}, headers=BFF
        )
        assert weak.status_code == 422 and "new_password" in weak.json()["error"]["fields"]
        assert (
            await local_client.post(
                self.REDEEM, json={"token": token, "new_password": NEW_PASSWORD}, headers=BFF
            )
        ).status_code == 204

    async def test_an_expired_link_is_dead(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        token = await self.issue(local_app, factory, account)
        async with factory() as db:
            await db.execute(
                update(LocalRecoveryToken).values(expires_at=utcnow() - dt.timedelta(seconds=1))
            )
            await db.commit()
        assert (
            await local_client.post(self.INSPECT, json={"token": token}, headers=BFF)
        ).status_code == 404
        assert (
            await local_client.post(
                self.REDEEM, json={"token": token, "new_password": NEW_PASSWORD}, headers=BFF
            )
        ).status_code == 404

    async def test_a_new_link_replaces_the_old_one(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        old = await self.issue(local_app, factory, account)
        new = await self.issue(local_app, factory, account)
        assert (
            await local_client.post(self.INSPECT, json={"token": old}, headers=BFF)
        ).status_code == 404
        assert (
            await local_client.post(self.INSPECT, json={"token": new}, headers=BFF)
        ).status_code == 200

    @pytest.mark.parametrize("token", ["", "short", "a" * 43, "a" * 129])
    async def test_a_link_that_was_never_issued_is_refused(
        self, local_client: httpx.AsyncClient, token: str
    ) -> None:
        response = await local_client.post(self.INSPECT, json={"token": token}, headers=BFF)
        assert response.status_code in (404, 422)

    async def test_the_token_is_stored_only_as_a_digest(
        self, local_app: Any, account: LocalIdentity, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        token = await self.issue(local_app, factory, account)
        async with factory() as db:
            row = (await db.scalars(select(LocalRecoveryToken))).one()
        assert row.token_hash == domain.token_digest(token) and token not in row.token_hash

    async def test_only_an_active_account_can_be_recovered(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        from identity.local_auth.errors import RecoveryInvalidError

        pending = await make_identity(
            local_app, factory, status="pending", path=PATH_PENDING, verified=False
        )
        async with factory() as db:
            row = await db.get(LocalIdentity, pending.seq)
            assert row is not None
            with pytest.raises(RecoveryInvalidError):
                await local_app.state.local_auth.issue_recovery(db, row, issued_by=None)


class TestOperatorRecoveryLink:
    """A way into someone's account, issued by someone else: the riskiest route in the provider.

    These run with real sign-ins and database-resolved grants — not signed headers — so that the
    scope each permission is held at, and how recently the operator typed their password, are the
    real thing.
    """

    def path(self, user_id: uuid.UUID) -> str:
        return f"/v1/users/{user_id}/password-recovery"

    async def staff(
        self,
        app: Any,
        factory: async_sessionmaker[AsyncSession],
        *,
        tenant: uuid.UUID,
        email: str,
        username: str,
        permissions: tuple[str, ...] = (),
        scope_type: str = "tenant",
        scope_id: uuid.UUID = SCOPE_ALL,
        grants: tuple[tuple[tuple[str, ...], str, uuid.UUID], ...] = (),
    ) -> tuple[uuid.UUID, LocalIdentity]:
        """A person with a local sign-in, a user row and any number of grants."""
        identity = await make_identity(app, factory, email=email, username=username)
        user = build_user(
            tenant_id=tenant, email=email, authentik_sub=identity.sub, user_type="tenant_admin"
        )
        wanted = list(grants)
        if permissions:
            wanted.append((permissions, scope_type, scope_id))
        async with factory() as db:
            db.add(user)
            await db.flush()
            for keys, kind, where in wanted:
                role = build_role(tenant_id=tenant, key=f"r{uuid.uuid4().hex[:10]}")
                db.add(role)
                await db.flush()
                for key in keys:
                    db.add(
                        build_role_permission(tenant_id=tenant, role_id=role.id, permission_key=key)
                    )
                db.add(
                    build_role_assignment(
                        tenant_id=tenant,
                        role_id=role.id,
                        subject_id=user.id,
                        scope_type=kind,
                        scope_id=where,
                    )
                )
            await db.commit()
        return user.id, identity

    async def world(
        self,
        app: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
        *,
        actor: tuple[tuple[str, ...], str, str] = (("user.update",), "tenant", ""),
        target: tuple[tuple[str, ...], str, str] = ((), "tenant", ""),
        extra_actor: tuple[tuple[str, ...], str, str] | None = None,
    ) -> World:
        """Two companies; an operator and a colleague, each with ``(permissions, scope, firm)``."""
        tenant = build_tenant(slug="alpha")
        company_a = build_company(tenant_id=tenant.id, code="A")
        company_b = build_company(tenant_id=tenant.id, code="B")
        async with factory() as db:
            db.add(tenant)
            await db.flush()
            db.add_all([company_a, company_b])
            await db.commit()
        companies = {"": SCOPE_ALL, "a": company_a.id, "b": company_b.id}

        def resolved(
            spec: tuple[tuple[str, ...], str, str],
        ) -> tuple[tuple[str, ...], str, uuid.UUID]:
            keys, kind, name = spec
            return keys, kind, companies[name]

        operator_grants = (resolved(actor),) + ((resolved(extra_actor),) if extra_actor else ())
        operator, _ = await self.staff(
            app,
            factory,
            tenant=tenant.id,
            email="boss@alpha.example",
            username="boss",
            grants=operator_grants,
        )
        colleague, identity = await self.staff(
            app,
            factory,
            tenant=tenant.id,
            email="ravi@alpha.example",
            username="ravi",
            grants=(resolved(target),) if target[0] else (),
        )
        issued = await tokens(client, "boss@alpha.example")
        return World(
            tenant=tenant.id,
            operator=operator,
            colleague=colleague,
            identity=identity,
            headers={"Authorization": f"Bearer {issued['access_token']}"},
        )

    async def test_an_administrator_gets_a_one_time_link_for_a_colleague(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        world = await self.world(local_app, local_client, factory)
        response = await local_client.post(
            self.path(world.colleague), json={"reason": "Locked out"}, headers=world.headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["recovery_url"].startswith(f"{UI}/reset?token=")
        assert (
            response.headers["cache-control"] == "no-store"
            and response.headers["referrer-policy"] == "no-referrer"
        )
        token = body["recovery_url"].split("token=")[1]
        async with factory() as db:
            row = (await db.scalars(select(LocalRecoveryToken))).one()
        assert row.token_hash == domain.token_digest(token) and row.issued_by == world.operator
        assert (
            await local_client.post(
                "/internal/v1/local-auth/password/recovery/inspect",
                json={"token": token},
                headers=BFF,
            )
        ).status_code == 200
        assert "user.password_recovery_requested" in await events(factory, world.tenant)

    async def test_it_needs_the_permission_and_a_reason(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        reader = await self.world(
            local_app, local_client, factory, actor=(("user.read",), "tenant", "")
        )
        denied = await local_client.post(
            self.path(reader.colleague), json={"reason": "x"}, headers=reader.headers
        )
        assert denied.status_code == 403
        async with factory() as db:
            assert list(await db.scalars(select(LocalRecoveryToken))) == []

    async def test_a_reason_is_required_and_an_anonymous_caller_is_refused(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        world = await self.world(local_app, local_client, factory)
        missing = await local_client.post(
            self.path(world.colleague), json={}, headers=world.headers
        )
        assert missing.status_code == 422
        anonymous = await local_client.post(self.path(world.colleague), json={"reason": "x"})
        assert anonymous.status_code == 401

    @pytest.mark.parametrize(
        ("actor", "target", "allowed"),
        [
            # Held at the same place, or the actor holds it more broadly: fine.
            (
                (("user.update", "journal.post"), "company", "a"),
                (("journal.post",), "company", "a"),
                True,
            ),
            (
                (("user.update", "journal.post"), "tenant", ""),
                (("journal.post",), "company", "b"),
                True,
            ),
            # The same permission somewhere the actor does not hold it: never.
            ((("user.update",), "tenant", ""), (("journal.post",), "company", "a"), False),
            (
                (("user.update", "journal.post"), "company", "a"),
                (("journal.post",), "company", "b"),
                False,
            ),
            (
                (("user.update", "journal.post"), "company", "a"),
                (("journal.post",), "tenant", ""),
                False,
            ),
            # A permission the actor does not hold at all.
            ((("user.update",), "tenant", ""), (("journal.post",), "tenant", ""), False),
        ],
    )
    async def test_it_never_reaches_authority_the_actor_does_not_hold_where_the_target_holds_it(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
        actor: tuple[tuple[str, ...], str, str],
        target: tuple[tuple[str, ...], str, str],
        allowed: bool,
    ) -> None:
        # `user.update` is needed at tenant scope to reach the route at all; a company-scoped actor
        # gets it through a second, tenant-wide grant that carries nothing else.
        needs_tenant = actor[1] != "tenant"
        world = await self.world(
            local_app,
            local_client,
            factory,
            actor=actor,
            target=target,
            extra_actor=(("user.update",), "tenant", "") if needs_tenant else None,
        )
        response = await local_client.post(
            self.path(world.colleague), json={"reason": "x"}, headers=world.headers
        )
        assert response.status_code == (200 if allowed else 403), response.text
        async with factory() as db:
            issued = list(await db.scalars(select(LocalRecoveryToken)))
        assert len(issued) == (1 if allowed else 0)
        if not allowed:
            # The refusal is the same whatever the target holds: it never names a permission.
            message = response.json()["error"]["message"]
            assert "journal" not in message and "post" not in message

    async def test_a_role_that_starts_tomorrow_counts_as_authority_the_target_already_has(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The link outlives today: reset a person on Monday, be them on Tuesday."""
        world = await self.world(local_app, local_client, factory)
        async with factory() as db:
            role = build_role(tenant_id=world.tenant, key="finance")
            db.add(role)
            await db.flush()
            db.add(
                build_role_permission(
                    tenant_id=world.tenant, role_id=role.id, permission_key="journal.post"
                )
            )
            db.add(
                build_role_assignment(
                    tenant_id=world.tenant,
                    role_id=role.id,
                    subject_id=world.colleague,
                    valid_from=utcnow().date() + dt.timedelta(days=1),
                )
            )
            await db.commit()
        refused = await local_client.post(
            self.path(world.colleague), json={"reason": "x"}, headers=world.headers
        )
        assert refused.status_code == 403
        async with factory() as db:
            assert list(await db.scalars(select(LocalRecoveryToken))) == []

    async def test_the_platform_operator_cannot_be_reset_by_someone_holding_the_same_role(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Operator status is configuration, not a grant: no permission comparison can see it."""
        world = await self.world(local_app, local_client, factory)
        allowed = await local_client.post(
            self.path(world.colleague), json={"reason": "x"}, headers=world.headers
        )
        assert allowed.status_code == 200  # the control: an ordinary colleague is fine
        monkeypatch.setitem(
            local_app.state.settings.platform_operators, world.identity.sub, world.colleague
        )
        refused = await local_client.post(
            self.path(world.colleague), json={"reason": "x"}, headers=world.headers
        )
        assert refused.status_code == 403
        assert "platform access page" in refused.json()["error"]["message"]

    async def test_the_administrator_setup_recorded_is_an_operator_too(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        world = await self.world(local_app, local_client, factory)
        async with factory() as db:
            db.add(
                build_platform_installation(
                    completed_at=utcnow(),
                    administrator_id=world.colleague,
                    administrator_subject=world.identity.sub,
                    tenant_id=world.tenant,
                )
            )
            await db.commit()
        refused = await local_client.post(
            self.path(world.colleague), json={"reason": "x"}, headers=world.headers
        )
        assert refused.status_code == 403

    async def test_the_completion_names_who_issued_the_link(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Redeeming is recorded as the account holder; the operator must still be traceable."""
        world = await self.world(local_app, local_client, factory)
        link = (
            await local_client.post(
                self.path(world.colleague), json={"reason": "Locked out"}, headers=world.headers
            )
        ).json()["recovery_url"]
        redeemed = await local_client.post(
            "/internal/v1/local-auth/password/recovery/redeem",
            json={"token": link.split("token=")[1], "new_password": NEW_PASSWORD},
            headers=BFF,
        )
        assert redeemed.status_code == 204
        async with factory() as db:
            rows = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type == "user.password_recovery_completed",
                        Outbox.tenant_id == world.tenant,
                    )
                )
            )
        assert len(rows) == 1 and str(world.operator) in str(rows[0].payload)

    async def test_it_refuses_yourself_an_inactive_user_and_a_user_without_a_local_account(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        world = await self.world(local_app, local_client, factory)
        # Yourself — who does have a local account, so only the rule itself can refuse it.
        assert (
            await local_client.post(
                self.path(world.operator), json={"reason": "x"}, headers=world.headers
            )
        ).status_code == 409
        async with factory() as db:
            await db.execute(
                update(User).where(User.id == world.colleague).values(status="deactivated")
            )
            await db.commit()
        assert (
            await local_client.post(
                self.path(world.colleague), json={"reason": "x"}, headers=world.headers
            )
        ).status_code == 409
        third = build_user(tenant_id=world.tenant, email="nolocal@alpha.example")
        async with factory() as db:
            db.add(third)
            await db.commit()
        assert (
            await local_client.post(
                self.path(third.id), json={"reason": "x"}, headers=world.headers
            )
        ).status_code == 409
        async with factory() as db:
            assert list(await db.scalars(select(LocalRecoveryToken))) == []

    async def test_it_needs_a_sign_in_from_the_last_few_minutes_not_just_a_live_session(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        world = await self.world(local_app, local_client, factory)
        issued = await tokens(local_client, "boss@alpha.example")
        # The password was typed ten minutes ago; the session has been refreshed since, which keeps
        # the original sign-in time, so this is what a stolen, kept-alive session looks like.
        async with factory() as db:
            await db.execute(
                update(LocalRefreshToken).values(
                    authenticated_at=utcnow() - dt.timedelta(minutes=10)
                )
            )
            await db.commit()
        renewed = (await refresh(local_client, issued["refresh_token"])).json()
        stale = {"Authorization": f"Bearer {renewed['access_token']}"}
        response = await local_client.post(
            self.path(world.colleague), json={"reason": "x"}, headers=stale
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "reauthentication_required"
        async with factory() as db:
            assert list(await db.scalars(select(LocalRecoveryToken))) == []
        # Signing in again is what makes it work.
        assert (
            await local_client.post(
                self.path(world.colleague), json={"reason": "x"}, headers=world.headers
            )
        ).status_code == 200

    async def test_another_tenants_user_is_not_found(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        world = await self.world(local_app, local_client, factory)
        other_tenant = build_tenant(slug="beta")
        outsider = build_user(tenant_id=other_tenant.id, email="out@beta.example")
        async with factory() as db:
            db.add(other_tenant)
            await db.flush()
            db.add(outsider)
            await db.commit()
        response = await local_client.post(
            self.path(outsider.id), json={"reason": "x"}, headers=world.headers
        )
        assert response.status_code == 404

    async def test_under_authentik_it_is_not_offered(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            self.path(uuid.uuid4()),
            json={"reason": "x"},
            headers=actor_headers(
                tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), grants=[grant(["user.update"])]
            ),
        )
        assert response.status_code in (404, 409)


@dataclass(frozen=True)
class World:
    tenant: uuid.UUID
    operator: uuid.UUID
    colleague: uuid.UUID
    identity: LocalIdentity
    headers: dict[str, str]


class TestOtherSignInMethods:
    async def test_social_links_are_not_offered_and_nothing_is_stored(
        self,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Linking is proven against the provider's own signed claim; the local one has none."""
        _, user = await attach_user(factory, account)
        issued = await tokens(local_client, EMAIL)
        response = await local_client.post(
            f"/v1/users/{user}/identities",
            json={"provider": "google", "provider_sub": "108123456789"},
            headers={"Authorization": f"Bearer {issued['access_token']}"},
        )
        assert response.status_code == 409
        assert "not available with local sign-in" in response.json()["error"]["message"]
        # The primary sign-in cannot be smuggled in as a "linked" Authentik identity either.
        smuggled = await local_client.post(
            f"/v1/users/{user}/identities",
            json={"provider": "authentik", "provider_sub": account.sub},
            headers={"Authorization": f"Bearer {issued['access_token']}"},
        )
        assert smuggled.status_code == 409


# --------------------------------------------------------------------------- first administrator


class TestSetupAdministrator:
    PATH = "/internal/v1/local-auth/setup/administrator"
    KEY = "setup-key-for-tests-only-0123456789abcdef"
    BODY: ClassVar[dict[str, str]] = {
        "name": "First Admin",
        "email": "root@alpha.example",
        "password": PASSWORD,
    }

    @pytest_asyncio.fixture
    async def ready(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[Any]:
        previous = local_app.state.settings.setup_key
        local_app.state.settings.setup_key = SecretStr(self.KEY)
        async with factory() as db:
            db.add(build_platform_installation())
            await db.commit()
        yield local_app
        local_app.state.settings.setup_key = previous

    async def test_the_key_creates_the_first_administrator_active_and_verified(
        self, ready: Any, local_client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        response = await local_client.post(
            self.PATH, json=self.BODY, headers={**BFF, "X-Setup-Key": self.KEY}
        )
        assert response.status_code == 201
        async with factory() as db:
            identity = (await db.scalars(select(LocalIdentity))).one()
        assert (
            identity.path == PATH_PLATFORM
            and identity.status == "active"
            and identity.email_verified_at is not None
        )
        status = (await local_client.get("/internal/v1/local-auth/status", headers=BFF)).json()
        assert status["setup"]["administrator_exists"] is True
        # …and that administrator can sign in.
        assert (
            await login(local_client, await begin(local_client), "root@alpha.example", PASSWORD)
        ).status_code == 200

    @pytest.mark.parametrize("key", [None, "", "wrong" * 8])
    async def test_without_the_right_key_nothing_is_created(
        self,
        ready: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
        key: str | None,
    ) -> None:
        headers = dict(BFF) | ({"X-Setup-Key": key} if key is not None else {})
        assert (
            await local_client.post(self.PATH, json=self.BODY, headers=headers)
        ).status_code == 403
        async with factory() as db:
            assert list(await db.scalars(select(LocalIdentity))) == []

    async def test_it_is_a_one_shot(self, ready: Any, local_client: httpx.AsyncClient) -> None:
        headers = {**BFF, "X-Setup-Key": self.KEY}
        assert (
            await local_client.post(self.PATH, json=self.BODY, headers=headers)
        ).status_code == 201
        second = await local_client.post(
            self.PATH, json=self.BODY | {"email": "other@alpha.example"}, headers=headers
        )
        assert second.status_code == 409

    async def test_it_is_closed_once_setup_is_complete(
        self, ready: Any, local_client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        from identity.models.platform_installation import PlatformInstallation

        async with factory() as db:
            await db.execute(update(PlatformInstallation).values(completed_at=utcnow()))
            await db.commit()
        response = await local_client.post(
            self.PATH, json=self.BODY, headers={**BFF, "X-Setup-Key": self.KEY}
        )
        assert response.status_code == 409

    async def test_without_a_configured_key_it_is_never_open(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with factory() as db:
            db.add(build_platform_installation())
            await db.commit()
        local_app.state.settings.setup_key = None
        response = await local_client.post(
            self.PATH, json=self.BODY, headers={**BFF, "X-Setup-Key": self.KEY}
        )
        assert response.status_code == 403

    async def test_a_weak_password_is_refused(
        self, ready: Any, local_client: httpx.AsyncClient
    ) -> None:
        response = await local_client.post(
            self.PATH,
            json=self.BODY | {"password": "123"},
            headers={**BFF, "X-Setup-Key": self.KEY},
        )
        assert response.status_code == 422 and "password" in response.json()["error"]["fields"]


_ = (tenant_scope, Tenant, LocalRefreshToken)
