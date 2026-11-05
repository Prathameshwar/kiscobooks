"""Two-tenant isolation for every Phase 8 to 10 table (CLAUDE.md §7).

Includes the SCOPE_ALL-scoped tables (``custom_field_definition``, ``field_config``): a
tenant-wide definition still belongs to one tenant and must never be visible to another.
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import (
    CustomFieldDefinition,
    CustomFieldSequence,
    CustomFieldValueIndex,
    FieldConfig,
    FieldPolicy,
    ImpersonationSession,
)
from tests.factories import (
    build_custom_field_definition,
    build_custom_field_sequence,
    build_custom_field_value_index,
    build_field_config,
    build_field_policy,
    build_impersonation_session,
    seed_two_tenants,
)

# No module-level asyncio mark: mixes async isolation tests (asyncio_mode="auto") with a
# synchronous sentinel check.


async def _count(session: AsyncSession, count_col: Any, tenant_id: uuid.UUID) -> int:
    with tenant_scope(tenant_id):
        return int(await session.scalar(select(func.count(count_col))) or 0)


async def test_phase8_9_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    with unfiltered():
        session.add(
            build_impersonation_session(
                tenant_id=tenant_a, actor_user_id=uuid7(), target_user_id=uuid7()
            )
        )
        session.add(
            build_impersonation_session(
                tenant_id=tenant_b, actor_user_id=uuid7(), target_user_id=uuid7()
            )
        )
        session.add(build_field_policy(tenant_id=tenant_a, subject_id=uuid7()))
        session.add(build_field_policy(tenant_id=tenant_b, subject_id=uuid7()))
        await session.commit()
    for model in (ImpersonationSession, FieldPolicy):
        assert await _count(session, model.id, tenant_a) == 1
        assert await _count(session, model.id, tenant_b) == 1


async def test_phase10_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    def_a, def_b = uuid7(), uuid7()
    company_a, company_b = uuid7(), uuid7()
    with unfiltered():
        # Tenant-wide definitions (company_id = SCOPE_ALL) still belong to one tenant.
        session.add(build_custom_field_definition(tenant_id=tenant_a, def_id=def_a, key="a_field"))
        session.add(build_custom_field_definition(tenant_id=tenant_b, def_id=def_b, key="b_field"))
        session.add(build_field_config(tenant_id=tenant_a))
        session.add(build_field_config(tenant_id=tenant_b))
        session.add(
            build_custom_field_sequence(
                tenant_id=tenant_a, definition_id=def_a, company_id=company_a
            )
        )
        session.add(
            build_custom_field_sequence(
                tenant_id=tenant_b, definition_id=def_b, company_id=company_b
            )
        )
        session.add(
            build_custom_field_value_index(
                tenant_id=tenant_a, definition_id=def_a, company_id=company_a
            )
        )
        session.add(
            build_custom_field_value_index(
                tenant_id=tenant_b, definition_id=def_b, company_id=company_b
            )
        )
        await session.commit()
    for model in (CustomFieldDefinition, FieldConfig, CustomFieldSequence):
        assert await _count(session, model.id, tenant_a) == 1
        assert await _count(session, model.id, tenant_b) == 1
    # value_index has a natural-key PK (no `id`) — count a PK column instead.
    assert await _count(session, CustomFieldValueIndex.entity_id, tenant_a) == 1
    assert await _count(session, CustomFieldValueIndex.entity_id, tenant_b) == 1


def test_scope_all_sentinel_is_stored_not_null() -> None:
    """The three SCOPE_ALL columns default to the sentinel, never NULL (db-plan §2)."""
    assert SCOPE_ALL == uuid.UUID(int=0)
    policy = build_field_policy(tenant_id=uuid7(), subject_id=uuid7())
    assert policy.scope_id == SCOPE_ALL
    definition = build_custom_field_definition(tenant_id=uuid7())
    assert definition.company_id == SCOPE_ALL
