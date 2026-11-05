"""Actual MySQL constraints and concurrent public Identity commands."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from identity.config import Settings
from identity.install import install_identity
from identity.main import create_app
from identity.models import CompanyFeature, Department, Membership, User
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET, actor_headers, grant
from tests.factories import (
    build_company,
    build_department,
    build_membership,
    build_tenant,
    build_user,
)


@pytest.mark.mysql
def test_ownership_constraints_and_concurrent_commands(mysql_url):
    install_identity(mysql_url)

    async def exercise():
        app = create_app(
            Settings(
                database_url=mysql_url,
                actor_signing_secret=SecretStr(ACTOR_SECRET),
                cursor_signing_secret=SecretStr(CURSOR_SECRET),
            )
        )
        (
            tenant,
            foreign,
            company,
            other,
            foreign_company,
            actor_id,
            user_id,
            another_user,
            foreign_user,
            a,
            b,
        ) = (uuid7() for _ in range(11))
        try:
            with unfiltered():
                async with app.state.session_factory() as db:
                    db.add_all(
                        [
                            build_tenant(tenant_id=tenant, slug=f"review-{tenant.hex}"),
                            build_tenant(tenant_id=foreign, slug=f"review-{foreign.hex}"),
                        ]
                    )
                    await db.flush()
                    db.add_all(
                        [
                            build_company(tenant_id=tenant, company_id=company, state_code="IN-MH"),
                            build_company(
                                tenant_id=tenant, company_id=other, code="OTHER", state_code="IN-MH"
                            ),
                            build_company(
                                tenant_id=foreign, company_id=foreign_company, state_code="IN-MH"
                            ),
                            build_user(
                                tenant_id=tenant, user_id=actor_id, email="actor@example.test"
                            ),
                            build_user(
                                tenant_id=tenant, user_id=user_id, email="user@example.test"
                            ),
                            build_user(
                                tenant_id=tenant, user_id=another_user, email="second@example.test"
                            ),
                            build_user(tenant_id=foreign, user_id=foreign_user),
                        ]
                    )
                    await db.flush()
                    db.add_all(
                        [
                            build_department(
                                tenant_id=tenant, company_id=company, department_id=a, code="A"
                            ),
                            build_department(
                                tenant_id=tenant, company_id=company, department_id=b, code="B"
                            ),
                        ]
                    )
                    await db.commit()
            # Raw writes bypass route guards: the database still rejects bad ownership.
            with unfiltered():
                async with app.state.session_factory() as db:
                    with pytest.raises(IntegrityError):
                        async with db.begin_nested():
                            user = await db.get(User, user_id)
                            user.default_company_id = foreign_company
                            await db.flush()
                    with pytest.raises(IntegrityError):
                        async with db.begin_nested():
                            user = await db.get(User, user_id)
                            user.default_company_id = other
                            user.default_department_id = a
                            await db.flush()
                    with pytest.raises(IntegrityError):
                        async with db.begin_nested():
                            department = await db.get(Department, a)
                            department.head_user_id = foreign_user
                            await db.flush()
                    db.add(
                        build_membership(
                            tenant_id=tenant, user_id=actor_id, company_id=company, is_primary=True
                        )
                    )
                    await db.commit()
                    with pytest.raises(IntegrityError):
                        async with db.begin_nested():
                            db.add(
                                build_membership(
                                    tenant_id=tenant,
                                    user_id=actor_id,
                                    company_id=company,
                                    is_primary=False,
                                )
                            )
                            await db.flush()
                    with pytest.raises(IntegrityError):
                        async with db.begin_nested():
                            db.add(
                                build_membership(
                                    tenant_id=tenant,
                                    user_id=actor_id,
                                    company_id=other,
                                    is_primary=True,
                                )
                            )
                            await db.flush()
            headers = actor_headers(
                tenant_id=tenant,
                user_id=actor_id,
                grants=[grant(["department.manage", "company.update", "company.read"])],
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://identity.test"
            ) as client:
                path = f"/v1/companies/{company}/memberships"
                responses = await asyncio.gather(
                    *(
                        client.post(path, headers=headers, json={"user_id": str(user_id)})
                        for _ in range(2)
                    )
                )
                assert sorted(r.status_code for r in responses) == [201, 409]
                responses = await asyncio.gather(
                    *(
                        client.post(
                            f"/v1/companies/{cid}/memberships",
                            headers=headers,
                            json={"user_id": str(another_user), "is_primary": True},
                        )
                        for cid in (company, other)
                    )
                )
                assert sorted(r.status_code for r in responses) == [201, 409]
                # Concurrent retries restore one assignment and stage one audit.
                from identity.models import Outbox
                from tests.factories import build_role, build_role_assignment, build_role_permission

                role_id, assignment_id = uuid7(), uuid7()
                with tenant_scope(tenant):
                    async with app.state.session_factory() as db:
                        db.add(build_role(tenant_id=tenant, role_id=role_id, key="restore_role"))
                        await db.flush()
                        db.add_all(
                            [
                                build_role_permission(
                                    tenant_id=tenant, role_id=role_id, permission_key="unit.manage"
                                ),
                                build_role_assignment(
                                    tenant_id=tenant,
                                    role_id=role_id,
                                    subject_id=user_id,
                                    id=assignment_id,
                                    is_active=False,
                                ),
                            ]
                        )
                        await db.commit()
                restore_headers = actor_headers(
                    tenant_id=tenant,
                    user_id=actor_id,
                    grants=[grant(["role.assign", "unit.manage"])],
                ) | {"Idempotency-Key": "concurrent-restore"}
                restore_path = f"/v1/role-assignments/{assignment_id}/regrant"
                restored = await asyncio.gather(
                    *(
                        client.post(
                            restore_path,
                            headers=restore_headers,
                            json={"reason": "Concurrent restoration"},
                        )
                        for _ in range(2)
                    )
                )
                assert [r.status_code for r in restored] == [200, 200], [
                    (r.status_code, r.text) for r in restored
                ]
                assert restored[0].json() == restored[1].json()
                with tenant_scope(tenant):
                    async with app.state.session_factory() as db:
                        events = list(
                            await db.scalars(
                                select(Outbox).where(
                                    Outbox.event_type == "role_assignment.regranted"
                                )
                            )
                        )
                        assert len(events) == 1
                # Reciprocal moves may never both pass their old-tree cycle checks.
                root = f"/v1/companies/{company}/departments"
                responses = await asyncio.gather(
                    client.post(
                        f"{root}/{a}/reparent", headers=headers, json={"parent_id": str(b)}
                    ),
                    client.post(
                        f"{root}/{b}/reparent", headers=headers, json={"parent_id": str(a)}
                    ),
                )
                assert sorted(r.status_code for r in responses) == [200, 409], [
                    (r.status_code, r.text) for r in responses
                ]
                # Race dependency enable against prerequisite disable, repeatedly.
                root = f"/v1/companies/{company}/features"
                for _ in range(6):
                    assert (
                        await client.post(root + "/inventory/enable", headers=headers)
                    ).status_code == 200
                    assert (
                        await client.post(root + "/batch_tracking/disable", headers=headers)
                    ).status_code == 200
                    responses = await asyncio.gather(
                        client.post(root + "/batch_tracking/enable", headers=headers),
                        client.post(root + "/inventory/disable", headers=headers),
                    )
                    assert all(r.status_code in (200, 422) for r in responses), [
                        (r.status_code, r.text) for r in responses
                    ]
                    with tenant_scope(tenant):
                        async with app.state.session_factory() as db:
                            rows = {
                                row.feature_key: row.is_enabled
                                for row in await db.scalars(
                                    select(CompanyFeature).where(
                                        CompanyFeature.company_id == company
                                    )
                                )
                            }
                            assert not rows.get("batch_tracking") or rows.get("inventory")
                with tenant_scope(tenant):
                    async with app.state.session_factory() as db:
                        depts = list(
                            await db.scalars(
                                select(Department).where(Department.company_id == company)
                            )
                        )
                        assert sum(row.parent_id is None for row in depts) == 1
                        memberships = list(
                            await db.scalars(
                                select(Membership).where(Membership.user_id == another_user)
                            )
                        )
                        assert sum(row.is_primary and row.is_active for row in memberships) == 1
        finally:
            await app.state.engine.dispose()

    asyncio.run(exercise())


@pytest.mark.mysql
def test_composite_owner_constraints_are_present(mysql_url):
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    from identity.models import CompanyTaxRegistration

    install_identity(mysql_url)

    async def verify():
        engine = create_async_engine(mysql_url)
        try:
            async with engine.connect() as conn:

                def inspect_constraints(connection):
                    inspector = inspect(connection)
                    for model in (User, Department, Membership, CompanyTaxRegistration):
                        actual = {
                            fk["name"]: (
                                fk["constrained_columns"],
                                fk["referred_table"],
                                fk["referred_columns"],
                            )
                            for fk in inspector.get_foreign_keys(model.__tablename__)
                        }
                        for constraint in model.__table__.foreign_key_constraints:
                            target = next(iter(constraint.elements)).column.table.name
                            expected = (
                                [col.name for col in constraint.columns],
                                target,
                                [element.column.name for element in constraint.elements],
                            )
                            assert actual[constraint.name] == expected
                    checks = {check["name"] for check in inspector.get_check_constraints("user")}
                    assert "ck_user_default_department_requires_company" in checks

                await conn.run_sync(inspect_constraints)
        finally:
            await engine.dispose()

    asyncio.run(verify())


@pytest.mark.mysql
def test_membership_upgrade_refuses_duplicates_without_deleting(mysql_url):
    from alembic import command
    from billing_platform.db import create_session_factory
    from sqlalchemy import func, insert, inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.alembic_support import alembic_config
    from tests.factories import seed_jurisdiction

    config = alembic_config(mysql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "0042")
    tenant, company, user = (uuid7() for _ in range(3))

    async def seed():
        engine = create_async_engine(mysql_url)
        try:
            with unfiltered():
                async with create_session_factory(engine)() as db:
                    await seed_jurisdiction(db)
                    db.add(build_tenant(tenant_id=tenant))
                    await db.flush()
                    db.add_all(
                        [
                            build_company(tenant_id=tenant, company_id=company),
                        ]
                    )
                    await db.flush()
                    # Revision 0042 predates token revocation: seed its historical columns.
                    historical_user = build_user(tenant_id=tenant, user_id=user)
                    values = {
                        column.key: getattr(historical_user, column.key)
                        for column in User.__table__.columns
                        if column.key != "tokens_valid_after_at"
                        and getattr(historical_user, column.key) is not None
                    }
                    await db.execute(insert(User.__table__).values(**values))
                    await db.commit()
            async with engine.begin() as conn:
                for _ in range(2):
                    await conn.execute(
                        insert(Membership).values(
                            id=uuid7(),
                            tenant_id=tenant,
                            user_id=user,
                            company_id=company,
                            department_id=None,
                            is_primary=False,
                            is_active=True,
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(seed())
    with pytest.raises(IntegrityError):
        command.upgrade(config, "0043")

    async def preserved():
        engine = create_async_engine(mysql_url)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(select(func.count()).select_from(Membership)) == 2
                columns = await conn.run_sync(lambda c: inspect(c).get_columns("membership"))
                assert "department_scope_key" not in {col["name"] for col in columns}
        finally:
            await engine.dispose()

    asyncio.run(preserved())
    command.downgrade(config, "base")
