"""Operating the local provider: key rotation, retirement and clean-up (docs/local-auth.md §6)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from billing_platform.db import unfiltered
from billing_platform.db.types import utcnow
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from identity.local_auth import adoption, cli, domain
from identity.models import Outbox, PlatformInstallation, User
from identity.models.local_auth import (
    PATH_ADMINISTRATORS,
    PATH_PENDING,
    PATH_PLATFORM,
    LocalAuthorization,
    LocalCredential,
    LocalIdentity,
    LocalRecoveryToken,
    LocalRefreshToken,
    LocalSigningKey,
)
from tests.factories import build_platform_installation, build_tenant, build_user
from tests.local_auth_support import BFF, PASSWORD, header_of, light_engine, refresh, tokens

EMAIL = "asha@alpha.example"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = await light_engine(enforce_foreign_keys=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def account(local_app: Any, factory: async_sessionmaker[AsyncSession]) -> LocalIdentity:
    async with factory() as db:
        identity = await local_app.state.local_auth.create_account(
            db,
            name="Asha",
            username="asha",
            email=EMAIL,
            password=PASSWORD,
            region=("IN", ""),
            workspace_name=None,
            path=PATH_ADMINISTRATORS,
            status="active",
            verified=True,
        )
        await db.commit()
        return identity


async def statuses(factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    async with factory() as db:
        return {row.kid: row.status for row in await db.scalars(select(LocalSigningKey))}


async def test_rotation_signs_with_a_new_key_and_keeps_every_earlier_token_valid(
    local_app: Any,
    local_client: httpx.AsyncClient,
    account: LocalIdentity,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    before = await tokens(local_client, EMAIL)
    first = next(iter(await statuses(factory)))

    new = await cli.rotate_key(factory, local_app.state.local_auth)
    local_app.state.local_auth.keys._cached = (
        None  # a fresh process would start with nothing in memory
    )

    state = await statuses(factory)
    assert state[first] == "retiring" and state[new] == "active"
    keys = (await local_client.get("/oidc/jwks")).json()["keys"]
    assert {key["kid"] for key in keys} == {first, new}
    # The old token still verifies against the published set; a new one is signed by the new key.
    await local_app.state.token_verifier.verify(before["access_token"])
    after = await refresh(local_client, before["refresh_token"])
    assert after.status_code == 200
    assert header_of(after.json()["access_token"])["kid"] == new
    await local_app.state.token_verifier.verify(after.json()["access_token"])


async def test_a_rotated_out_key_is_retired_only_after_its_last_token_could_have_expired(
    local_app: Any,
    local_client: httpx.AsyncClient,
    account: LocalIdentity,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await local_client.get("/oidc/jwks")
    first = next(iter(await statuses(factory)))
    new = await cli.rotate_key(factory, local_app.state.local_auth)

    assert await cli.retire_keys(factory, local_app.state.local_auth) == 0  # rotated a moment ago
    async with factory() as db:
        await db.execute(
            update(LocalSigningKey)
            .where(LocalSigningKey.kid == first)
            .values(retired_at=utcnow() - dt.timedelta(minutes=30))
        )
        await db.commit()
    assert await cli.retire_keys(factory, local_app.state.local_auth) == 1
    assert await statuses(factory) == {first: "retired", new: "active"}
    local_app.state.local_auth.keys._cached = None
    assert {key["kid"] for key in (await local_client.get("/oidc/jwks")).json()["keys"]} == {new}


async def test_purge_removes_only_rows_that_are_long_spent(
    local_app: Any,
    local_client: httpx.AsyncClient,
    account: LocalIdentity,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    live = await tokens(local_client, EMAIL)
    old = utcnow() - dt.timedelta(days=30)
    async with factory() as db:
        service = local_app.state.local_auth
        stored = (await db.scalars(select(LocalIdentity))).one()
        await service.issue_recovery(db, stored, issued_by=None)
        await db.execute(update(LocalRecoveryToken).values(expires_at=old))
        await service.issue_recovery(db, stored, issued_by=None)
        db.add(
            LocalAuthorization(
                request_hash="e" * 64,
                client_id="billing-web",
                redirect_uri="http://x",
                scope="openid",
                state="s",
                nonce="n",
                code_challenge="c" * 43,
                expires_at=old,
            )
        )
        await db.commit()
    counts = await cli.purge(factory)
    assert (
        counts["authorizations"] >= 1
        and counts["recovery_tokens"] >= 1
        and counts["refresh_tokens"] == 0
    )
    assert (await refresh(local_client, live["refresh_token"])).status_code == 200


async def test_purge_never_touches_an_unexpired_refresh_token_even_if_it_was_revoked_recently(
    local_app: Any,
    local_client: httpx.AsyncClient,
    account: LocalIdentity,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await tokens(local_client, EMAIL)
    async with factory() as db:
        await db.execute(update(LocalRefreshToken).values(revoked_at=utcnow()))
        await db.commit()
    assert (await cli.purge(factory))["refresh_tokens"] == 0
    async with factory() as db:
        assert len(list(await db.scalars(select(LocalRefreshToken)))) == 1


class TestResetSetupAdministrator:
    """A mistyped password before setup completes must not strand the installation."""

    async def administrator(
        self, app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> LocalIdentity:
        async with factory() as db:
            identity = await app.state.local_auth.create_administrator(
                db,
                name="Priya Nair",
                email="priya@owner.example",
                password=PASSWORD,
                path=PATH_PLATFORM,
            )
            await app.state.local_auth.issue_recovery(db, identity, issued_by=None)
            await db.commit()
            return identity

    async def test_an_unused_administrator_is_forgotten_with_everything_that_hangs_off_it(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await self.administrator(local_app, factory)
        await tokens(local_client, "priya@owner.example")
        async with factory() as db:
            db.add(build_platform_installation())
            await db.commit()
        message = await cli.reset_setup_administrator(factory)
        assert "Removed 1" in message
        async with factory() as db:
            for model in (LocalIdentity, LocalCredential, LocalRecoveryToken, LocalRefreshToken):
                assert list(await db.scalars(select(model))) == [], model

    async def test_it_does_not_touch_an_ordinary_account(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        account: LocalIdentity,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with factory() as db:
            db.add(build_platform_installation())
            await db.commit()
        assert "Removed 0" in await cli.reset_setup_administrator(factory)
        async with factory() as db:
            assert len(list(await db.scalars(select(LocalIdentity)))) == 1

    async def test_it_refuses_once_setup_has_completed(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await self.administrator(local_app, factory)
        async with factory() as db:
            db.add(build_platform_installation(completed_at=utcnow()))
            await db.commit()
        assert "completed" in await cli.reset_setup_administrator(factory)
        async with factory() as db:
            assert len(list(await db.scalars(select(LocalIdentity)))) == 1

    async def test_it_refuses_an_account_a_user_already_points_at(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        identity = await self.administrator(local_app, factory)
        tenant = build_tenant(slug="owner")
        async with factory() as db:
            db.add_all([build_platform_installation(), tenant])
            await db.flush()
            db.add(
                build_user(tenant_id=tenant.id, email=identity.email, authentik_sub=identity.sub)
            )
            await db.commit()
        assert "already linked" in await cli.reset_setup_administrator(factory)
        async with factory() as db:
            assert len(list(await db.scalars(select(LocalIdentity)))) == 1


class TestAdoptUsers:
    """Moving an installation that ran on Authentik: the people must be able to get back in."""

    OLD_SUB = "authentik-subject-of-the-platform-administrator"

    async def installation(
        self, app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> dict[str, uuid.UUID]:
        """A completed installation: a platform administrator and two colleagues, one inactive."""
        tenant = build_tenant(slug="owner")
        admin = build_user(
            tenant_id=tenant.id,
            email="Priya@Owner.Example",
            authentik_sub=self.OLD_SUB,
            display_name="Priya Nair",
        )
        colleague = build_user(
            tenant_id=tenant.id, email="ravi@owner.example", authentik_sub="authentik-ravi"
        )
        gone = build_user(
            tenant_id=tenant.id,
            email="gone@owner.example",
            authentik_sub="authentik-gone",
            status="deactivated",
        )
        async with factory() as db:
            db.add(tenant)
            await db.flush()
            db.add_all([admin, colleague, gone])
            await db.flush()
            db.add(
                build_platform_installation(
                    completed_at=utcnow(),
                    tenant_id=tenant.id,
                    administrator_id=admin.id,
                    administrator_subject=self.OLD_SUB,
                )
            )
            await db.commit()
        return {"tenant": tenant.id, "admin": admin.id, "colleague": colleague.id, "gone": gone.id}

    async def run(
        self, app: Any, factory: async_sessionmaker[AsyncSession], **options: Any
    ) -> list[Any]:
        return await adoption.adopt_users(
            factory, app.state.local_auth, app.state.settings, **options
        )

    async def user(self, factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> Any:
        with unfiltered():
            async with factory() as db:
                return await db.get(User, user_id)

    async def test_by_default_only_the_platform_administrator_moves_and_can_then_sign_in(
        self,
        local_app: Any,
        local_client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        ids = await self.installation(local_app, factory)
        results = await self.run(local_app, factory)
        assert [(r.email, r.platform_operator, r.skipped) for r in results] == [
            ("Priya@Owner.Example", True, None)
        ]
        link = results[0].link
        assert link is not None and "/reset?token=" in link
        # Nobody else was touched, and the old subject no longer names the administrator.
        assert (await self.user(factory, ids["colleague"])).authentik_sub == "authentik-ravi"
        admin = await self.user(factory, ids["admin"])
        assert admin.authentik_sub == results[0].new_subject != self.OLD_SUB
        assert admin.tokens_valid_after_at is not None
        async with factory() as db:
            identity = (await db.scalars(select(LocalIdentity))).one()
            installation = (await db.scalars(select(PlatformInstallation))).one()
        assert identity.path == PATH_PLATFORM and identity.status == "active"
        assert identity.email == "priya@owner.example" and identity.email_verified_at is not None
        assert installation.administrator_subject == identity.sub  # the recorded operator follows

        # The person chooses a password through the link, then signs in as the same user row.
        redeemed = await local_client.post(
            "/internal/v1/local-auth/password/recovery/redeem",
            json={"token": link.split("token=")[1], "new_password": "a password of my own"},
            headers=BFF,
        )
        assert redeemed.status_code == 204
        issued = await tokens(local_client, "priya@owner.example", "a password of my own")
        session = await local_client.get(
            "/v1/session", headers={"Authorization": f"Bearer {issued['access_token']}"}
        )
        assert session.status_code == 200 and session.json()["user"]["id"] == str(ids["admin"])

    async def test_the_password_the_account_starts_with_is_one_nobody_knows(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await self.installation(local_app, factory)
        await self.run(local_app, factory)
        async with factory() as db:
            credential = (await db.scalars(select(LocalCredential))).one()
        assert credential.password_hash.startswith("$argon2id$")
        for guess in ("x", "password", "Priya Nair", "priya@owner.example", self.OLD_SUB):
            assert not domain.verify_password(credential.password_hash, guess)

    async def test_named_people_and_everyone_move_but_not_the_inactive_or_the_already_moved(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        ids = await self.installation(local_app, factory)
        named = await self.run(local_app, factory, emails=["RAVI@owner.example"])
        assert [(r.email, r.platform_operator) for r in named] == [("ravi@owner.example", False)]
        async with factory() as db:
            ravi = (
                await db.scalars(
                    select(LocalIdentity).where(LocalIdentity.email == "ravi@owner.example")
                )
            ).one()
        assert ravi.path == PATH_ADMINISTRATORS
        everyone = await self.run(local_app, factory, everyone=True)
        by_email = {r.email: r for r in everyone}
        assert by_email["ravi@owner.example"].skipped == "already signs in locally"
        assert by_email["ravi@owner.example"].link is None
        assert by_email["Priya@Owner.Example"].link is not None
        assert "gone@owner.example" not in by_email  # deactivated people are not brought back
        assert (await self.user(factory, ids["gone"])).authentik_sub == "authentik-gone"
        # A second run finds nothing left to do and issues no new link.
        again = await self.run(local_app, factory, everyone=True)
        assert all(r.link is None and r.skipped == "already signs in locally" for r in again)

    async def test_an_email_a_different_local_account_uses_is_not_linked_automatically(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        ids = await self.installation(local_app, factory)
        async with factory() as db:
            await local_app.state.local_auth.create_account(
                db,
                name="Someone Else",
                username="someone",
                email="priya@owner.example",
                password="whatever it is 1",
                region=("IN", ""),
                workspace_name=None,
                path=PATH_PENDING,
                status="pending",
                verified=False,
            )
            await db.commit()
        results = await self.run(local_app, factory)
        assert results[0].link is None and "another local account" in str(results[0].skipped)
        assert (await self.user(factory, ids["admin"])).authentik_sub == self.OLD_SUB

    async def test_the_move_is_audited_against_the_person(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        ids = await self.installation(local_app, factory)
        await self.run(local_app, factory)
        async with factory() as db:
            rows = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type == "user.sign_in_provider_changed",
                        Outbox.tenant_id == ids["tenant"],
                    )
                )
            )
        assert len(rows) == 1 and str(ids["admin"]) in str(rows[0].payload)

    async def test_an_operator_named_in_the_environment_is_told_how_to_update_it(
        self,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ids = await self.installation(local_app, factory)
        configured = {"authentik-ravi": ids["colleague"], self.OLD_SUB: ids["admin"]}
        monkeypatch.setattr(local_app.state.settings, "platform_operators", configured)
        results = await self.run(local_app, factory)
        assert {r.email for r in results} == {"Priya@Owner.Example", "ravi@owner.example"}
        mapping = adoption.operator_settings(local_app.state.settings, results)
        assert mapping is not None
        assert set(mapping.values()) == {str(i) for i in configured.values()}
        assert self.OLD_SUB not in mapping and "authentik-ravi" not in mapping
        report = cli.adoption_report(local_app.state.settings, results)
        assert "IDENTITY_PLATFORM_OPERATORS" in report
        assert all(subject in report for subject in mapping)

    async def test_the_report_carries_the_links_and_says_so_plainly_when_there_is_nobody(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        # A fresh installation with no recorded administrator and nothing configured.
        none = await self.run(local_app, factory)
        assert none == []
        assert "Nobody to move" in cli.adoption_report(local_app.state.settings, none)
        await self.installation(local_app, factory)
        moved = await self.run(local_app, factory)
        report = cli.adoption_report(local_app.state.settings, moved)
        assert moved[0].link is not None and moved[0].link in report
        assert "[platform administrator]" in report and "works once" in report
