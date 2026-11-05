"""The account review, administrator provisioning and recovery workflows over local accounts.

The state machine, its reconciliation and the audit are the existing ones; only the provider behind
them changed. So these tests drive the *real* review API (``/v1/platform/accounts``) with the local
provider selected, and the adapter classes directly for the rest. Each names what could go wrong:
an approval that leaves the account unable to sign in, a rejection that reads as "pending", a
provisioning retry that resets someone's live password.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.local_auth import domain
from identity.local_auth.adapters import (
    LocalAccountProvider,
    LocalAdministratorProvider,
    LocalRecoveryProvider,
)
from identity.local_auth.service import LocalAuth
from identity.models import AccountReview, User
from identity.models.local_auth import (
    PATH_ADMINISTRATORS,
    PATH_PENDING,
    LocalCredential,
    LocalIdentity,
)
from identity.services.account_provider import AccountProviderUnavailableError
from identity.services.administrator_provider import AdministratorProviderUnavailableError
from identity.services.administrator_recovery import AdministratorRecoveryUnavailableError
from tests.local_auth_support import PASSWORD, begin, local_settings
from tests.test_account_review_api import review_app  # noqa: F401  (a fixture)
from tests.test_platform_setup import signed

pytest_plugins = ["tests.test_platform_setup"]


async def sign_up(
    service: LocalAuth,
    factory: async_sessionmaker[AsyncSession],
    *,
    email: str = "ravi@beta.example",
    username: str = "ravi",
    workspace: str | None = "North Books",
) -> LocalIdentity:
    async with factory() as db:
        identity = await service.create_account(
            db,
            name="Ravi Menon",
            username=username,
            email=email,
            password=PASSWORD,
            region=("IN", ""),
            workspace_name=workspace,
            path=PATH_PENDING,
            status="pending",
            verified=False,
        )
        await db.commit()
        return identity


@pytest.fixture
def local_review(review_app: Any) -> Any:  # noqa: F811
    """The review app, switched to the local provider."""
    app, key, operating_tenant = review_app
    app.state.settings.auth_provider = "local"
    app.state.settings.local_auth = local_settings()
    app.state.local_auth = LocalAuth(app.state.settings.local_auth)
    return app, key, operating_tenant


async def decide(
    client: httpx.AsyncClient, key: Any, row_id: str, action: str, version: int = 1, **extra: Any
) -> httpx.Response:
    body = {
        "action": action,
        "version": version,
        "reason": "Independently verified the applicant",
        "attested": True,
    } | extra
    return await client.post(
        f"/v1/platform/accounts/{row_id}/review",
        json=body,
        headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
    )


class TestReviewWorkflowOverLocalAccounts:
    async def test_sync_imports_a_local_sign_up_and_approval_makes_a_working_administrator(
        self,
        local_review: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        app, key, _ = local_review
        identity = await sign_up(app.state.local_auth, factory)

        synced = await client.post("/v1/platform/accounts/sync", headers=signed(key))
        assert synced.status_code == 200 and synced.json()["imported"] == 1
        listing = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"]
        assert [item["email"] for item in listing] == ["ravi@beta.example"]
        row = listing[0]
        assert row["status"] == "pending" and row["needs_attention"] is False

        approved = await decide(client, key, row["id"], "approve", workspace_name="North Books")
        assert approved.status_code == 202, approved.text
        assert approved.json()["status"] == "approved"

        async with factory() as db:
            stored = await db.get(LocalIdentity, identity.seq)
            assert (
                stored is not None
                and stored.status == "active"
                and stored.email_verified_at is not None
            )
            assert stored.review_command is not None
        with unfiltered():
            async with factory() as db:
                admin = await db.scalar(select(User).where(User.authentik_sub == identity.sub))
        assert admin is not None and admin.status == "active" and admin.email == "ravi@beta.example"

        # And the approved person can now actually sign in through the provider.
        request_id = await begin(client)
        signed_in = await client.post(
            "/internal/v1/local-auth/login",
            json={"request_id": request_id, "email": "ravi@beta.example", "password": PASSWORD},
            headers={"X-Auth-Bff-Secret": local_settings().bff_secret.get_secret_value()},
        )
        assert signed_in.status_code == 200, signed_in.text

    async def test_rejection_leaves_a_sign_up_that_cannot_sign_in_and_does_not_read_as_pending(
        self,
        local_review: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        app, key, _ = local_review
        identity = await sign_up(app.state.local_auth, factory)
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
        row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]

        rejected = await decide(client, key, row["id"], "reject")
        assert rejected.status_code == 202 and rejected.json()["status"] == "rejected"

        async with factory() as db:
            stored = await db.get(LocalIdentity, identity.seq)
        assert (
            stored is not None and stored.status == "disabled" and stored.email_verified_at is None
        )
        login = await client.post(
            "/internal/v1/local-auth/login",
            json={
                "request_id": await begin(client),
                "email": "ravi@beta.example",
                "password": PASSWORD,
            },
            headers={"X-Auth-Bff-Secret": local_settings().bff_secret.get_secret_value()},
        )
        assert login.status_code == 403 and login.json()["error"]["code"] == "account_disabled"

    async def test_a_rejected_sign_up_can_be_reopened_and_is_then_pending_again(
        self,
        local_review: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        app, key, _ = local_review
        identity = await sign_up(app.state.local_auth, factory)
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
        row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
        await decide(client, key, row["id"], "reject")
        version = (
            await client.get(f"/v1/platform/accounts/{row['id']}", headers=signed(key))
        ).json()["version"]

        reopened = await decide(client, key, row["id"], "reopen", version=version)
        assert reopened.status_code == 202 and reopened.json()["status"] == "pending"
        async with factory() as db:
            stored = await db.get(LocalIdentity, identity.seq)
        assert stored is not None and stored.status == "pending"

    async def test_an_account_edited_after_import_is_flagged_not_approved(
        self,
        local_review: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        app, key, _ = local_review
        identity = await sign_up(app.state.local_auth, factory)
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
        row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
        async with factory() as db:
            stored = await db.get(LocalIdentity, identity.seq)
            assert stored is not None
            stored.name = "Someone Else"
            await db.commit()

        result = await decide(client, key, row["id"], "approve", workspace_name="North Books")
        assert result.status_code == 202
        assert result.json()["history"][0]["status"] == "blocked"
        async with factory() as db:
            stored = await db.get(LocalIdentity, identity.seq)
        assert stored is not None and stored.status == "pending"

    async def test_an_administrator_or_platform_account_never_appears_for_review(
        self,
        local_review: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        app, key, _ = local_review
        async with factory() as db:
            await app.state.local_auth.create_administrator(
                db,
                name="Root",
                email="root@alpha.example",
                password=PASSWORD,
                path=PATH_ADMINISTRATORS,
            )
            await db.commit()
        await sign_up(app.state.local_auth, factory)
        synced = await client.post("/v1/platform/accounts/sync", headers=signed(key))
        assert synced.json()["imported"] == 1


class TestPlatformAdministratorRecovery:
    async def approved_administrator(
        self,
        app: Any,
        key: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> tuple[uuid.UUID, uuid.UUID, LocalIdentity]:
        identity = await sign_up(app.state.local_auth, factory)
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
        row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
        approved = await decide(client, key, row["id"], "approve", workspace_name="North Books")
        assert approved.status_code == 202, approved.text
        with unfiltered():
            async with factory() as db:
                user = await db.scalar(select(User).where(User.authentik_sub == identity.sub))
        assert user is not None
        return user.tenant_id, user.id, identity

    async def test_the_operator_is_offered_a_link_and_never_an_email_and_gets_a_working_one(
        self,
        local_review: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        app, key, _ = local_review
        tenant_id, user_id, identity = await self.approved_administrator(app, key, client, factory)
        path = f"/v1/platform/access/tenants/{tenant_id}/administrators/{user_id}"
        detail = (await client.get(path, headers=signed(key))).json()
        assert detail["recovery_deliveries"] == ["link"]

        body = {
            "delivery": "link",
            "reason": "Locked out of the console",
            "expected_updated_at": detail["updated_at"],
            "expected_assignment_updated_at": detail["assignment_updated_at"],
        }
        response = await client.post(path + "/password-recovery", json=body, headers=signed(key))
        assert response.status_code == 200, response.text
        link = response.json()["recovery_url"]
        assert link.startswith("http://localhost:4310/reset?token=")
        token = link.split("token=")[1]
        redeemed = await client.post(
            "/internal/v1/local-auth/password/recovery/redeem",
            json={"token": token, "new_password": "a recovered passphrase"},
            headers={"X-Auth-Bff-Secret": local_settings().bff_secret.get_secret_value()},
        )
        assert redeemed.status_code == 204
        async with factory() as db:
            stored = await db.get(LocalCredential, identity.seq)
        assert stored is not None and domain.verify_password(
            stored.password_hash, "a recovered passphrase"
        )

        fresh = (await client.get(path, headers=signed(key))).json()
        emailed = await client.post(
            path + "/password-recovery",
            json=body
            | {
                "delivery": "email",
                "expected_updated_at": fresh["updated_at"],
                "expected_assignment_updated_at": fresh["assignment_updated_at"],
            },
            headers=signed(key),
        )
        assert emailed.status_code in (409, 503) and "link" in emailed.text.lower()

    async def test_without_the_local_provider_configured_no_delivery_is_offered(
        self,
        local_review: Any,
        client: httpx.AsyncClient,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        app, key, _ = local_review
        tenant_id, user_id, _ = await self.approved_administrator(app, key, client, factory)
        app.state.settings.local_auth = None
        detail = (
            await client.get(
                f"/v1/platform/access/tenants/{tenant_id}/administrators/{user_id}",
                headers=signed(key),
            )
        ).json()
        assert detail["recovery_deliveries"] == []


class TestAccountProvider:
    @pytest.fixture
    def provider(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> LocalAccountProvider:
        return LocalAccountProvider(factory)

    async def test_pages_pending_sign_ups_newest_first_with_a_next_page_flag(
        self,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        provider: LocalAccountProvider,
    ) -> None:
        for index in range(3):
            await sign_up(
                local_app.state.local_auth,
                factory,
                email=f"p{index}@beta.example",
                username=f"person{index}",
            )
        rows, more = await provider.page(1)
        assert [row.email for row in rows] == [
            "p2@beta.example",
            "p1@beta.example",
            "p0@beta.example",
        ]
        assert more is False
        assert all(row.path == PATH_PENDING and row.user_type == "external" for row in rows)

    async def test_exact_pending_email_lookup_ignores_case_and_active_accounts(
        self,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        provider: LocalAccountProvider,
    ) -> None:
        await sign_up(local_app.state.local_auth, factory)
        assert [row.email for row in await provider.pending_email("RAVI@Beta.Example")] == [
            "ravi@beta.example"
        ]
        assert await provider.pending_email("nobody@beta.example") == []
        async with factory() as db:
            identity = (await db.scalars(select(LocalIdentity))).one()
            identity.status = "active"
            await db.commit()
        assert await provider.pending_email("ravi@beta.example") == []

    async def test_read_returns_the_marker_the_reconciler_looks_for_and_a_subject(
        self,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        provider: LocalAccountProvider,
    ) -> None:
        identity = await sign_up(local_app.state.local_auth, factory)
        applicant, raw = await provider.read(identity.seq)
        assert applicant.provider_uuid == identity.uid and applicant.provider_id == identity.seq
        assert applicant.is_active is False and applicant.verified is False
        assert raw["attributes"] == {"billing_account_review_command": None}
        assert provider.subject(raw) == identity.sub

    async def test_an_account_outside_the_review_scope_cannot_be_read(
        self,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        provider: LocalAccountProvider,
    ) -> None:
        async with factory() as db:
            admin = await local_app.state.local_auth.create_administrator(
                db,
                name="Root",
                email="root@alpha.example",
                password=PASSWORD,
                path=PATH_ADMINISTRATORS,
            )
            await db.commit()
        with pytest.raises(AccountProviderUnavailableError):
            await provider.read(admin.seq)
        with pytest.raises(AccountProviderUnavailableError):
            await provider.read(99_999)

    @pytest.mark.parametrize(
        "raw", [{}, {"sub": None}, {"sub": "short"}, {"sub": "G" * 64}, {"sub": "a" * 63}]
    )
    async def test_a_subject_that_is_not_64_hex_is_refused(
        self, provider: LocalAccountProvider, raw: dict[str, Any]
    ) -> None:
        with pytest.raises(AccountProviderUnavailableError):
            provider.subject(raw)

    async def test_apply_refuses_when_the_identity_changed_underneath_the_decision(
        self,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        provider: LocalAccountProvider,
    ) -> None:
        identity = await sign_up(local_app.state.local_auth, factory)
        _, raw = await provider.read(identity.seq)
        raw["uuid"] = str(uuid.uuid4())
        with pytest.raises(AccountProviderUnavailableError):
            await provider.apply(
                identity.seq, raw, active=True, verified=True, command_id=uuid.uuid4()
            )

    async def test_apply_activates_and_verifies_or_disables(
        self,
        local_app: Any,
        factory: async_sessionmaker[AsyncSession],
        provider: LocalAccountProvider,
    ) -> None:
        identity = await sign_up(local_app.state.local_auth, factory)
        _, raw = await provider.read(identity.seq)
        marker = uuid.uuid4()
        await provider.apply(identity.seq, raw, active=True, verified=True, command_id=marker)
        applicant, _ = await provider.read(identity.seq)
        assert applicant.is_active is True and applicant.verified is True
        async with factory() as db:
            stored = await db.get(LocalIdentity, identity.seq)
        assert (
            stored is not None
            and stored.status == "active"
            and stored.email_verified_at is not None
        )
        assert stored.review_command == str(marker)


class TestAdministratorProvider:
    @pytest.fixture
    def provider(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> LocalAdministratorProvider:
        return LocalAdministratorProvider(factory, local_app.state.local_auth)

    async def test_create_makes_an_inactive_verified_account_until_activation(
        self, provider: LocalAdministratorProvider, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        marker = uuid.uuid4()
        username, subject = await provider.create(
            email="Boss@Alpha.example", name="Boss", password=PASSWORD, marker=marker
        )
        assert username == LocalAdministratorProvider.username_for("boss@alpha.example")
        row = await provider.by_email("boss@alpha.example")
        assert row is not None and row["is_active"] is False and row["uid"] == subject
        assert row["attributes"] == {
            "billing_email_verified": True,
            "billing_tenant_provision_command": str(marker),
        }
        with pytest.raises(ConflictError):  # not active yet, so it is not an "existing account"
            provider.confirm(row, "boss@alpha.example")
        await provider.activate(email="boss@alpha.example", marker=marker, subject=subject)
        active = await provider.by_email("boss@alpha.example")
        assert active is not None and provider.confirm(active, "boss@alpha.example") == (
            active["pk"],
            subject,
        )

    async def test_a_retry_with_the_same_marker_is_idempotent_and_resets_only_an_inactive_password(
        self, provider: LocalAdministratorProvider, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        marker = uuid.uuid4()
        first = await provider.create(
            email="boss@alpha.example", name="Boss", password=PASSWORD, marker=marker
        )
        second = await provider.create(
            email="boss@alpha.example", name="Boss", password="a second one!", marker=marker
        )
        assert first == second
        async with factory() as db:
            credential = (await db.scalars(select(LocalCredential))).one()
        assert domain.verify_password(credential.password_hash, "a second one!")
        # Once activated, a replayed request must not reach in and reset a live password.
        await provider.activate(email="boss@alpha.example", marker=marker, subject=first[1])
        await provider.create(
            email="boss@alpha.example", name="Boss", password="a third one!!", marker=marker
        )
        async with factory() as db:
            credential = (await db.scalars(select(LocalCredential))).one()
        assert domain.verify_password(credential.password_hash, "a second one!")
        assert not domain.verify_password(credential.password_hash, "a third one!!")

    async def test_an_email_already_used_by_someone_else_is_a_conflict(
        self,
        local_app: Any,
        provider: LocalAdministratorProvider,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await sign_up(
            local_app.state.local_auth, factory, email="boss@alpha.example", username="boss"
        )
        with pytest.raises(ConflictError):
            await provider.create(
                email="boss@alpha.example", name="Boss", password=PASSWORD, marker=uuid.uuid4()
            )

    async def test_another_marker_on_the_same_email_is_refused(
        self, provider: LocalAdministratorProvider
    ) -> None:
        await provider.create(
            email="boss@alpha.example", name="Boss", password=PASSWORD, marker=uuid.uuid4()
        )
        with pytest.raises(ConflictError):
            await provider.create(
                email="boss@alpha.example", name="Boss", password=PASSWORD, marker=uuid.uuid4()
            )

    async def test_activation_checks_the_marker_the_subject_and_that_the_account_exists(
        self, provider: LocalAdministratorProvider
    ) -> None:
        marker = uuid.uuid4()
        _, subject = await provider.create(
            email="boss@alpha.example", name="Boss", password=PASSWORD, marker=marker
        )
        with pytest.raises(ConflictError):
            await provider.activate(
                email="boss@alpha.example", marker=uuid.uuid4(), subject=subject
            )
        with pytest.raises(ConflictError):
            await provider.activate(email="boss@alpha.example", marker=marker, subject="0" * 64)
        with pytest.raises(AdministratorProviderUnavailableError):
            await provider.activate(email="ghost@alpha.example", marker=marker, subject=subject)

    @pytest.mark.parametrize(
        "change",
        [
            {"is_active": False},
            {"email": "other@alpha.example"},
            {"uid": "short"},
            {"pk": "1"},
            {"attributes": {"billing_email_verified": False}},
            {"attributes": None},
        ],
    )
    def test_confirm_refuses_an_account_that_is_not_an_active_verified_user(
        self, provider: LocalAdministratorProvider, change: dict[str, Any]
    ) -> None:
        row: dict[str, Any] = {
            "pk": 1,
            "uid": "a" * 64,
            "email": "boss@alpha.example",
            "is_active": True,
            "attributes": {"billing_email_verified": True},
        }
        with pytest.raises(ConflictError):
            provider.confirm(row | change, "boss@alpha.example")

    async def test_a_weak_password_is_refused_before_anything_is_created(
        self, provider: LocalAdministratorProvider, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        from billing_platform.errors import ValidationFailedError

        with pytest.raises(ValidationFailedError):
            await provider.create(
                email="boss@alpha.example", name="Boss", password="123", marker=uuid.uuid4()
            )
        async with factory() as db:
            assert list(await db.scalars(select(LocalIdentity))) == []


class TestRecoveryProvider:
    @pytest.fixture
    def provider(
        self, local_app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> LocalRecoveryProvider:
        return LocalRecoveryProvider(factory, local_app.state.local_auth)

    async def active_admin(
        self, app: Any, factory: async_sessionmaker[AsyncSession]
    ) -> LocalIdentity:
        async with factory() as db:
            identity = await app.state.local_auth.create_administrator(
                db,
                name="Boss",
                email="boss@alpha.example",
                password=PASSWORD,
                path=PATH_ADMINISTRATORS,
            )
            await db.commit()
            return identity

    async def test_a_link_is_issued_for_an_active_administrator(
        self,
        local_app: Any,
        provider: LocalRecoveryProvider,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await self.active_admin(local_app, factory)
        url, expires = await provider.recover(admin.sub, "link", "Boss@Alpha.example")
        assert url is not None and url.startswith("http://localhost:4310/reset?token=")
        assert expires.tzinfo is not None

    async def test_email_delivery_is_not_available_yet_and_says_to_use_a_link(
        self,
        local_app: Any,
        provider: LocalRecoveryProvider,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await self.active_admin(local_app, factory)
        with pytest.raises(AdministratorRecoveryUnavailableError, match="recovery link"):
            await provider.recover(admin.sub, "email", "boss@alpha.example")

    @pytest.mark.parametrize("email", ["other@alpha.example", ""])
    async def test_the_expected_email_must_match_the_account(
        self,
        local_app: Any,
        provider: LocalRecoveryProvider,
        factory: async_sessionmaker[AsyncSession],
        email: str,
    ) -> None:
        admin = await self.active_admin(local_app, factory)
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await provider.recover(admin.sub, "link", email)

    async def test_an_unknown_inactive_or_unverified_account_is_refused(
        self,
        local_app: Any,
        provider: LocalRecoveryProvider,
        factory: async_sessionmaker[AsyncSession],
    ) -> None:
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await provider.recover("a" * 64, "link", "boss@alpha.example")
        admin = await self.active_admin(local_app, factory)
        async with factory() as db:
            stored = await db.get(LocalIdentity, admin.seq)
            assert stored is not None
            stored.email_verified_at = None
            await db.commit()
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await provider.recover(admin.sub, "link", "boss@alpha.example")
        async with factory() as db:
            stored = await db.get(LocalIdentity, admin.seq)
            assert stored is not None
            stored.email_verified_at = domain_now()
            stored.status = "disabled"
            await db.commit()
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await provider.recover(admin.sub, "link", "boss@alpha.example")

    def test_only_64_hex_subjects_are_recoverable(self) -> None:
        assert LocalRecoveryProvider.subject_field("a" * 64) == "sub"
        assert LocalRecoveryProvider.subject_field(uuid.uuid4()) is None
        assert LocalRecoveryProvider.subject_field("short") is None


def domain_now() -> Any:
    from billing_platform.db.types import utcnow

    return utcnow()


_ = (tenant_scope, AccountReview)
