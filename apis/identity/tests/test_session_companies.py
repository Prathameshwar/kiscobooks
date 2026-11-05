"""``GET /v1/session/companies`` — the switcher's own list (docs/company-context-ui-todo D2).

The case that matters is the one the UI phase could not serve: a clerk holds no
``company.read`` at all, so the company list is a 403 for them and their switcher was
empty. They still have to be able to say which of their two companies they are in.
"""

from __future__ import annotations

import uuid

from billing_platform.db import tenant_scope

from identity.models import Company
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_department,
    build_field_policy,
    build_user,
    seed_two_companies,
)


async def test_clerk_without_company_read_sees_only_the_companies_they_work_in(
    client, session, tenant_a, tenant_b
):
    main, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        second = build_company(tenant_id=tenant_a, code="BBB", display_name="Bravo Ltd")
        third = build_company(tenant_id=tenant_a, code="CCC", display_name="Charlie Ltd")
        user = build_user(tenant_id=tenant_a)
        session.add_all([second, third, user])
        await session.commit()
        second_id, third_id, user_id = second.id, third.id, user.id
        (await session.get(Company, second_id)).requires_step_up = True
        await session.commit()
    clerk = actor_headers(
        tenant_id=tenant_a,
        user_id=user_id,
        grants=[
            grant(["invoice.create"], scope_type="company", scope_id=second_id),
            grant(["invoice.create"], scope_type="company", scope_id=third_id),
        ],
    )
    # The company list itself is still refused — this endpoint is not a way around it.
    assert (await client.get("/v1/companies", headers=clerk)).status_code == 403
    response = await client.get("/v1/session/companies", headers=clerk)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["code"] for item in body["items"]] == ["BBB", "CCC"]
    assert {item["id"] for item in body["items"]} == {str(second_id), str(third_id)}
    assert str(main) not in {item["id"] for item in body["items"]}
    assert str(foreign) not in {item["id"] for item in body["items"]}
    # A company that will demand a proof is marked before it is chosen.
    marked = next(item for item in body["items"] if item["id"] == str(second_id))
    assert marked["requires_step_up"] is True
    assert marked["is_default"] is False
    assert set(marked) == {"id", "code", "display_name", "requires_step_up", "is_default"}

    # The stored default is marked, so the switcher can say which row is the user's own.
    with tenant_scope(tenant_a):
        from identity.models import User

        (await session.get(User, user_id)).default_company_id = third_id
        await session.commit()
    body = (await client.get("/v1/session/companies", headers=clerk)).json()
    assert [item["is_default"] for item in body["items"]] == [False, True]


async def test_tenant_wide_actor_sees_every_open_listed_company(
    client, session, tenant_a, tenant_b
):
    main, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        hidden = build_company(
            tenant_id=tenant_a, code="HID", display_name="Hidden Ltd", visibility="unlisted"
        )
        closed = build_company(
            tenant_id=tenant_a, code="CLO", display_name="Closed Ltd", status="inactive"
        )
        user = build_user(tenant_id=tenant_a)
        session.add_all([hidden, closed, user])
        await session.commit()
        user_id = user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["invoice.create"])])
    body = (await client.get("/v1/session/companies", headers=headers)).json()
    # Unlisted is a display preference and a closed company cannot be worked in: neither
    # belongs in a switcher, and neither of them is this tenant's only company.
    assert [item["id"] for item in body["items"]] == [str(main)]
    assert str(foreign) not in {item["id"] for item in body["items"]}


async def test_department_grant_resolves_to_its_company(client, session, tenant_a, tenant_b):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        department = build_department(tenant_id=tenant_a, company_id=main)
        user = build_user(tenant_id=tenant_a)
        session.add_all([department, user])
        await session.commit()
        department_id, user_id = department.id, user.id
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=user_id,
        grants=[grant(["invoice.create"], scope_type="department", scope_id=department_id)],
    )
    body = (await client.get("/v1/session/companies", headers=headers)).json()
    assert [item["id"] for item in body["items"]] == [str(main)]


async def test_no_authority_and_lapsed_authority_both_return_an_empty_page(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.commit()
        user_id = user.id
    bare = await client.get(
        "/v1/session/companies", headers=actor_headers(tenant_id=tenant_a, user_id=user_id)
    )
    assert bare.status_code == 200, bare.text
    assert bare.json() == {"items": [], "page": {"next_cursor": None, "has_more": False}}
    lapsed = actor_headers(
        tenant_id=tenant_a,
        user_id=user_id,
        grants=[
            grant(
                ["invoice.create"],
                scope_type="company",
                scope_id=main,
                valid_to="2000-01-02",
            )
        ],
    )
    assert (await client.get("/v1/session/companies", headers=lapsed)).json()["items"] == []


async def test_search_and_paging_are_bounded_and_cursor_bound_to_this_list(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        second = build_company(tenant_id=tenant_a, code="BBB", display_name="Bravo Ltd")
        user = build_user(tenant_id=tenant_a)
        session.add_all([second, user])
        await session.commit()
        user_id = user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["invoice.create"])])
    first = (await client.get("/v1/session/companies?limit=1", headers=headers)).json()
    assert [item["code"] for item in first["items"]] == ["BBB"]
    assert first["page"]["has_more"] is True
    nxt = (
        await client.get(
            f"/v1/session/companies?limit=1&cursor={first['page']['next_cursor']}",
            headers=headers,
        )
    ).json()
    assert [item["code"] for item in nxt["items"]] == ["MAIN"]
    assert nxt["page"]["has_more"] is False
    # Search is a prefix on the switcher's own fields.
    found = (await client.get("/v1/session/companies?q=Bra", headers=headers)).json()
    assert [item["code"] for item in found["items"]] == ["BBB"]
    assert (await client.get("/v1/session/companies?q=B", headers=headers)).status_code == 422
    assert (await client.get("/v1/session/companies?limit=500", headers=headers)).status_code == 422
    # A cursor minted for the company list is not a cursor for this one.
    companies = (
        await client.get(
            "/v1/companies?limit=1&sort=code",
            headers=actor_headers(
                tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read"])]
            ),
        )
    ).json()
    crossed = await client.get(
        f"/v1/session/companies?limit=1&cursor={companies['page']['next_cursor']}", headers=headers
    )
    assert crossed.status_code == 422, crossed.text


async def test_unknown_user_and_unsigned_caller_are_refused(client, session, tenant_a, tenant_b):
    await seed_two_companies(session, tenant_a, tenant_b)
    assert (await client.get("/v1/session/companies")).status_code == 401
    missing = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["invoice.create"])]
    )
    assert (await client.get("/v1/session/companies", headers=missing)).status_code == 404


async def test_a_read_denied_name_is_not_searchable_by_an_actor_without_company_read(
    client, session, tenant_a, tenant_b
):
    """A prefix search is a read (CLAUDE.md invariant 15).

    The projection strips a denied field correctly, but set membership across prefixes
    reconstructs it one character at a time — and the deny check the company list relies on
    skips any company where `company.read` is not held, which is every company for the roles
    this endpoint was built for.
    """
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        clerk = build_user(tenant_id=tenant_a, email="clerk@example.test")
        session.add(clerk)
        await session.flush()
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="user",
                subject_id=clerk.id,
                entity_type="identity.company",
                field_key="display_name",
                access="read",
                effect="deny",
            )
        )
        await session.commit()
        clerk_id = clerk.id
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=clerk_id,
        grants=[grant(["invoice.create"], scope_type="company", scope_id=main)],
    )
    # The list itself still works, with the denied field absent from the row.
    listed = await client.get("/v1/session/companies", headers=headers)
    assert listed.status_code == 200, listed.text
    assert "display_name" not in listed.json()["items"][0]
    # Searching it is refused rather than silently answered.
    assert (await client.get("/v1/session/companies?q=Alp", headers=headers)).status_code == 403


async def test_legal_name_is_not_searchable_on_the_switcher_list(
    client, session, tenant_a, tenant_b
):
    """The list never returns `legal_name`, so matching on it would be a read with no row."""
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.commit()
        user_id = user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["invoice.create"])])
    with tenant_scope(tenant_a):
        assert (await session.get(Company, main)).legal_name == "Acme Traders Private Limited"
    # Its own `display_name` and `code` match; its legal name does not.
    assert (await client.get("/v1/session/companies?q=Alpha", headers=headers)).json()["items"]
    assert (await client.get("/v1/session/companies?q=MAIN", headers=headers)).json()["items"]
    assert (await client.get("/v1/session/companies?q=Acme", headers=headers)).json()["items"] == []
