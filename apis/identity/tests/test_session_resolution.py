"""``GET /v1/session``'s company resolution chain (identity/services/session_context.py).

Every rule of the chain is reachable only by arranging rows, never by clicking around, so
each of the four is asserted here together with the two cases the console could not tell
apart before: a stale default that must fall through, and a live one that needs a proof.
"""

from __future__ import annotations

import uuid

from billing_platform.db import tenant_scope

from identity.models import Company, Tenant, User
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_country,
    build_currency,
    build_membership,
    build_state,
    build_user,
    seed_two_companies,
)


async def test_session_location_defaults_are_from_the_authenticated_tenant(
    client, session, tenant_a, tenant_b
):
    await seed_two_companies(session, tenant_a, tenant_b)
    session.add(build_currency("GBP", numeric_code="826"))
    await session.flush()
    session.add(build_country("GB", "GBP", iso3="GBR", numeric_code="826"))
    await session.flush()
    session.add(build_state("ENG", "GB", name="England"))
    await session.flush()
    users = []
    for tenant_id, country, state in ((tenant_a, "IN", "MH"), (tenant_b, "GB", "ENG")):
        with tenant_scope(tenant_id):
            tenant = await session.get(Tenant, tenant_id)
            tenant.default_country_code, tenant.default_state_code = country, state
            user = build_user(tenant_id=tenant_id)
            session.add(user)
            await session.flush()
            users.append(user.id)
    await session.commit()
    for tenant_id, user_id, country, state in (
        (tenant_a, users[0], "IN", "MH"),
        (tenant_b, users[1], "GB", "ENG"),
    ):
        response = await client.get(
            "/v1/session",
            headers=actor_headers(
                tenant_id=tenant_id, user_id=user_id, grants=[grant(["company.create"])]
            ),
        )
        assert response.status_code == 200, response.text
        assert response.json()["tenant"]["default_country_code"] == country
        assert response.json()["tenant"]["default_state_code"] == state


async def test_chain_prefers_explicit_then_default_then_membership_then_first(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        early = build_company(tenant_id=tenant_a, code="AAA", display_name="Aardvark Ltd")
        later = build_company(tenant_id=tenant_a, code="ZZZ", display_name="Zenith Ltd")
        user = build_user(tenant_id=tenant_a)
        session.add_all([early, later, user])
        await session.commit()
        early_id, later_id, user_id = early.id, later.id, user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read"])])

    # 4. Nothing stored anywhere: the first readable company by `code`, which is the row
    # the switcher shows first — not an arbitrary one.
    body = (await client.get("/v1/session", headers=headers)).json()
    assert body["selected_source"] == "first"
    assert body["company"]["id"] == str(early_id)
    assert body["selected_company_id"] == str(early_id)
    assert body["step_up_required"] is False

    # 3. Where this person works outranks alphabetical order.
    with tenant_scope(tenant_a):
        session.add(build_membership(tenant_id=tenant_a, user_id=user_id, company_id=later_id))
        await session.commit()
    body = (await client.get("/v1/session", headers=headers)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("membership", str(later_id))

    # 2. Their own stored default outranks their workplace.
    with tenant_scope(tenant_a):
        (await session.get(User, user_id)).default_company_id = main
        await session.commit()
    body = (await client.get("/v1/session", headers=headers)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("default", str(main))

    # 1. An explicit switch outranks everything, and does not disturb the stored default.
    body = (await client.get(f"/v1/session?company_id={early_id}", headers=headers)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("explicit", str(early_id))
    with tenant_scope(tenant_a):
        session.expire_all()
        assert (await session.get(User, user_id)).default_company_id == main


async def test_stale_default_falls_through_but_a_step_up_default_is_named(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        fallback = build_company(tenant_id=tenant_a, code="ZZZ", display_name="Zenith Ltd")
        session.add(fallback)
        await session.flush()
        user = build_user(tenant_id=tenant_a, default_company_id=main)
        session.add(user)
        await session.flush()
        session.add(build_membership(tenant_id=tenant_a, user_id=user.id, company_id=fallback.id))
        await session.commit()
        fallback_id, user_id = fallback.id, user.id
    headers = actor_headers(tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read"])])

    # A deactivated default is stale, not a dead end: it must not strand the session.
    with tenant_scope(tenant_a):
        (await session.get(Company, main)).status = "inactive"
        await session.commit()
    body = (await client.get("/v1/session", headers=headers)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("membership", str(fallback_id))

    # A default that only needs a fresh proof is a live selection. It is named back with
    # `step_up_required`, never silently replaced by a different company.
    with tenant_scope(tenant_a):
        company = await session.get(Company, main)
        company.status, company.requires_step_up = "active", True
        await session.commit()
    response = await client.get("/v1/session", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["company"] is None
    assert body["step_up_required"] is True
    assert body["selected_source"] == "default"
    assert body["selected_company_id"] == str(main)
    # The same company asked for explicitly is refused instead, so a caller learns their
    # switch did not happen rather than reading an unchanged page as success.
    assert (await client.get(f"/v1/session?company_id={main}", headers=headers)).status_code == 403


async def test_chain_never_reaches_an_unreadable_or_foreign_company(
    client, session, tenant_a, tenant_b
):
    main, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        early = build_company(tenant_id=tenant_a, code="AAA", display_name="Aardvark Ltd")
        scoped_user = build_user(tenant_id=tenant_a, email="scoped@example.test")
        bare_user = build_user(tenant_id=tenant_a, email="bare@example.test")
        session.add_all([early, scoped_user, bare_user])
        await session.commit()
        early_id, scoped_id, bare_id = early.id, scoped_user.id, bare_user.id
    with tenant_scope(tenant_b):
        neighbour = build_user(tenant_id=tenant_b, email="neighbour@example.test")
        session.add(neighbour)
        await session.commit()
        neighbour_id = neighbour.id

    # A company-scoped reader lands on the company their grant names, not on the
    # alphabetically first company in the tenant.
    scoped = actor_headers(
        tenant_id=tenant_a,
        user_id=scoped_id,
        grants=[grant(["company.read"], scope_type="company", scope_id=main)],
    )
    body = (await client.get("/v1/session", headers=scoped)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("first", str(main))
    assert body["company"]["id"] != str(early_id)

    # A membership without an assignment reaches nothing (the Phase 6 exit test): the
    # chain checks `company.read` at the company's own scope, not the affiliation.
    with tenant_scope(tenant_a):
        session.add(build_membership(tenant_id=tenant_a, user_id=bare_id, company_id=main))
        await session.commit()
    body = (
        await client.get("/v1/session", headers=actor_headers(tenant_id=tenant_a, user_id=bare_id))
    ).json()
    assert body["selected_source"] == "none"
    assert body["company"] is None and body["selected_company_id"] is None

    # A lapsed grant narrows to no company at all rather than to every company.
    lapsed = actor_headers(
        tenant_id=tenant_a,
        user_id=scoped_id,
        grants=[
            grant(
                ["company.read"],
                scope_type="company",
                scope_id=main,
                valid_to="2000-01-02",
            )
        ],
    )
    assert (await client.get("/v1/session", headers=lapsed)).json()["selected_source"] == "none"

    # Cross-tenant: a tenant-wide reader in B resolves B's company and never A's.
    body = (
        await client.get(
            "/v1/session",
            headers=actor_headers(
                tenant_id=tenant_b, user_id=neighbour_id, grants=[grant(["company.read"])]
            ),
        )
    ).json()
    assert body["company"]["id"] == str(foreign)
    assert body["company"]["id"] not in {str(main), str(early_id)}
    # Asking for A's company by id from B is a 404-shaped miss, never a read.
    crossed = await client.get(
        f"/v1/session?company_id={main}",
        headers=actor_headers(
            tenant_id=tenant_b, user_id=neighbour_id, grants=[grant(["company.read"])]
        ),
    )
    assert crossed.status_code == 200, crossed.text
    assert crossed.json()["company"] is None


async def test_unknown_user_is_refused_before_any_company_is_resolved(
    client, session, tenant_a, tenant_b
):
    await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["company.read"])]
    )
    assert (await client.get("/v1/session", headers=headers)).status_code == 404
