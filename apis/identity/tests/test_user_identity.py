"""``user_identity`` — isolation, and the global uniqueness that makes login unambiguous.

``uq_user_identity_provider_provider_sub`` is the security-critical constraint on this
table and it is **global**: login arrives as ``(provider, provider_sub)`` and resolves to
a user, so a per-tenant key would let one Google account resolve to two accounts in two
tenants. The cross-tenant duplicate test is the one that matters here.
"""

from __future__ import annotations

import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import IDENTITY_PROVIDERS, Tenant, UserIdentity
from tests.factories import build_user, build_user_identity, seed_two_tenants


async def _one_user_per_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    user_a, user_b = uuid7(), uuid7()
    await seed_two_tenants(session, tenant_a, tenant_b)
    with unfiltered():
        session.add_all(
            [
                build_user(tenant_id=tenant_a, user_id=user_a, email="asha@alpha.example"),
                build_user(tenant_id=tenant_b, user_id=user_b, email="bo@beta.example"),
            ]
        )
        await session.commit()
    return user_a, user_b


# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_identity_links(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    user_a, user_b = await _one_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_user_identity(tenant_id=tenant_a, user_id=user_a, provider_sub="google-a"),
                build_user_identity(tenant_id=tenant_b, user_id=user_b, provider_sub="google-b"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(UserIdentity))).scalars().all()

    assert [row.provider_sub for row in rows] == ["google-a"]


async def test_the_other_tenants_identity_link_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A provider subject is not a credential, but it identifies a real account at a real
    provider — which is enough to enumerate a competitor's staff."""
    user_a, user_b = await _one_user_per_tenant(session, tenant_a, tenant_b)
    theirs = build_user_identity(tenant_id=tenant_b, user_id=user_b, provider_sub="google-b")

    with unfiltered():
        session.add_all(
            [theirs, build_user_identity(tenant_id=tenant_a, user_id=user_a, provider_sub="a")]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(UserIdentity).where(UserIdentity.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(UserIdentity.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_an_identity_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    user_a, _ = await _one_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_user_identity(tenant_id=tenant_a, user_id=user_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(UserIdentity))


async def test_every_identity_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    user_a, user_b = await _one_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_user_identity(tenant_id=tenant_a, user_id=user_a, provider_sub="a"),
                build_user_identity(tenant_id=tenant_b, user_id=user_b, provider_sub="b"),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(UserIdentity.tenant_id))).scalars().all())

    assert owners
    assert owners <= tenants


# --- the unique key -----------------------------------------------------------


async def test_one_provider_subject_cannot_belong_to_two_users_across_tenants(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**The load-bearing test in this file.** A per-tenant unique key would permit this
    row, and the login it describes would then resolve to whichever of the two the
    callback happened to read."""
    user_a, user_b = await _one_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_user_identity(tenant_id=tenant_a, user_id=user_a, provider_sub="shared-sub")
        )
        await session.commit()

        session.add(
            build_user_identity(tenant_id=tenant_b, user_id=user_b, provider_sub="shared-sub")
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_the_same_subject_string_at_two_providers_is_two_links(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Subjects are only unique within a provider's own namespace, so the key is the
    pair. A unique on ``provider_sub`` alone would refuse a legitimate second link."""
    user_a, _ = await _one_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_user_identity(
                    tenant_id=tenant_a, user_id=user_a, provider="google", provider_sub="12345"
                ),
                build_user_identity(
                    tenant_id=tenant_a, user_id=user_a, provider="microsoft", provider_sub="12345"
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (await session.execute(select(func.count(UserIdentity.id)))).scalar_one()

    assert counted == 2


async def test_a_link_must_belong_to_a_real_user(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await _one_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_user_identity(tenant_id=tenant_a, user_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# --- what the table refuses to hold -------------------------------------------


def test_the_table_holds_a_subject_and_no_token() -> None:
    """CLAUDE.md §5.9 and §5.11. A subject is a public identifier at the provider, so a
    leak of this table authenticates nobody. An access or refresh token here would make
    it a credential store — and one that logging would have to know to redact."""
    columns = set(table_of(UserIdentity).c.keys())
    forbidden = {"access_token", "refresh_token", "id_token", "secret", "client_secret", "password"}

    assert "provider_sub" in columns
    assert not columns & forbidden


def test_the_documented_providers_are_the_ones_the_code_knows() -> None:
    """Extended by adding a provider here and configuring it in Authentik — never by
    accepting whatever string a client sends, which would let a caller invent a provider
    namespace and collide with a real one."""
    assert IDENTITY_PROVIDERS == {"authentik", "google", "microsoft"}


def test_the_table_has_no_lifecycle_switch_because_unlinking_is_a_delete() -> None:
    """Rule 4.12. An identity link is not referenced by a posted document, so unlinking
    a provider removes the row — and leaving a deactivated row behind would keep its
    subject occupying the global unique key, silently refusing a relink."""
    columns = set(table_of(UserIdentity).c.keys())

    assert not columns & {"status", "is_active", "valid_from", "valid_to"}
