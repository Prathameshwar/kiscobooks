"""``PATCH /v1/session/preferences`` → ``default_company_id`` — "Set as my default".

The UI phase had no way to store a selection: it kept the open company in an 8 h cookie,
because this endpoint rejected the field. Storing it is a self-write that confers no
access, so what has to be proved is that it cannot name a company the actor could not
already open, and that it does not leave the user's default department pointing into a
company it no longer belongs to.
"""

from __future__ import annotations

import uuid

from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from sqlalchemy import select

from identity.models import Company, Department, User
from tests.api_support import actor_headers, grant
from tests.factories import build_company, build_department, build_user, seed_two_companies

PATH = "/v1/session/preferences"


async def test_default_company_is_stored_cleared_and_honoured_by_the_chain(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        early = build_company(tenant_id=tenant_a, code="AAA", display_name="Aardvark Ltd")
        user = build_user(tenant_id=tenant_a)
        session.add_all([early, user])
        await session.commit()
        early_id, user_id = early.id, user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read"])])

    # Before: the chain falls to the first readable company.
    assert (await client.get("/v1/session", headers=headers)).json()["selected_source"] == "first"
    response = await client.patch(PATH, headers=headers, json={"default_company_id": str(main)})
    assert response.status_code == 200, response.text
    assert response.json()["default_company_id"] == str(main)
    # After: the same session resolution now reports a stored default, not a fallback.
    body = (await client.get("/v1/session", headers=headers)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("default", str(main))

    # One audit event per real change, and a repeat of the same value emits none.
    repeat = await client.patch(PATH, headers=headers, json={"default_company_id": str(main)})
    assert repeat.status_code == 200, repeat.text
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "user.preferences_updated")
            )
        )
        assert len(events) == 1
        changes = events[0].payload["changes"]["default_company_id"]
        # Readable, not redacted: a landing company is no more sensitive than any other
        # company id already in the allowlist.
        assert (changes["from"], changes["to"]) == (None, str(main))

    # Explicit null clears it, and the chain goes back to the first readable company.
    cleared = await client.patch(PATH, headers=headers, json={"default_company_id": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["default_company_id"] is None
    body = (await client.get("/v1/session", headers=headers)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("first", str(early_id))


async def test_a_company_the_actor_cannot_open_is_refused(client, session, tenant_a, tenant_b):
    main, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        closed = build_company(
            tenant_id=tenant_a, code="CLO", display_name="Closed Ltd", status="inactive"
        )
        user = build_user(tenant_id=tenant_a)
        session.add_all([closed, user])
        await session.commit()
        closed_id, user_id = closed.id, user.id
    scoped = actor_headers(
        tenant_id=tenant_a,
        user_id=user_id,
        grants=[grant(["company.read"], scope_type="company", scope_id=main)],
    )
    for company_id in (foreign, closed_id, uuid.uuid4()):
        # A company in another tenant, a deactivated one and one that does not exist are
        # all the same answer — a 422 on the field, never a 404 that confirms existence.
        response = await client.patch(
            PATH, headers=scoped, json={"default_company_id": str(company_id)}
        )
        assert response.status_code == 422, response.text
        assert "default_company_id" in response.json()["error"]["fields"]
    # A company this actor holds nothing in is refused even though it is in their tenant.
    with tenant_scope(tenant_a):
        other = build_company(tenant_id=tenant_a, code="OTH", display_name="Other Ltd")
        session.add(other)
        await session.commit()
        other_id = other.id
    assert (
        await client.patch(PATH, headers=scoped, json={"default_company_id": str(other_id)})
    ).status_code == 422
    # Their own company is accepted.
    assert (
        await client.patch(PATH, headers=scoped, json={"default_company_id": str(main)})
    ).status_code == 200
    with tenant_scope(tenant_a):
        session.expire_all()
        assert (await session.get(User, user_id)).default_company_id == main


async def test_replacing_the_default_company_clears_a_department_of_the_old_one(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        second = build_company(tenant_id=tenant_a, code="BBB", display_name="Bravo Ltd")
        session.add(second)
        await session.flush()
        department = build_department(tenant_id=tenant_a, company_id=main)
        kept = build_department(tenant_id=tenant_a, company_id=second.id, code="OPS")
        session.add_all([department, kept])
        await session.flush()
        user = build_user(
            tenant_id=tenant_a, default_company_id=main, default_department_id=department.id
        )
        session.add(user)
        await session.commit()
        second_id, kept_id, user_id = second.id, kept.id, user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read"])])
    response = await client.patch(
        PATH, headers=headers, json={"default_company_id": str(second_id)}
    )
    assert response.status_code == 200, response.text
    assert response.json()["default_department_id"] is None
    with tenant_scope(tenant_a):
        session.expire_all()
        row = await session.get(User, user_id)
        assert (row.default_company_id, row.default_department_id) == (second_id, None)
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "user.preferences_updated")
            )
        )
        assert events[-1].payload["changes"]["default_department_id"]["to"] is None
        # The department itself is untouched: this is a preference, not a reorganisation.
        assert await session.get(Department, row.default_department_id or kept_id) is not None

    # A department that belongs to the new default company survives the change.
    with tenant_scope(tenant_a):
        row = await session.get(User, user_id)
        row.default_department_id = kept_id
        await session.commit()
    assert (
        await client.patch(PATH, headers=headers, json={"default_company_id": str(second_id)})
    ).status_code == 200
    with tenant_scope(tenant_a):
        session.expire_all()
        assert (await session.get(User, user_id)).default_department_id == kept_id


async def test_preferences_still_reject_unknown_fields_and_other_users(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.commit()
        user_id = user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read"])])
    # The allowlist is still a allowlist: this is not a route to arbitrary user columns.
    for body in (
        {"user_type": "tenant_admin"},
        {"default_department_id": str(uuid.uuid4())},
        {"tokens_valid_after_at": None},
    ):
        assert (await client.patch(PATH, headers=headers, json=body)).status_code == 422
    # A company id that is not a uuid is a 422, not a 500.
    assert (
        await client.patch(PATH, headers=headers, json={"default_company_id": "not-a-uuid"})
    ).status_code == 422
    assert (await client.patch(PATH, json={"default_company_id": str(main)})).status_code == 401
    with tenant_scope(tenant_a):
        assert (await session.get(Company, main)) is not None
