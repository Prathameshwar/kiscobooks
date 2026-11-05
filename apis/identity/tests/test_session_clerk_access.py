"""A clerk's company context end to end — the case the switcher exists for.

The seeded clerk, approver, accounts-clerk and controller roles hold **no** ``company.read``
(docs/roles-permissions.md §4). A switcher that lists their companies and then refuses to open
one is not a switcher, so what is asserted here is that one rule — "any authority in this
company" — answers the list, the resolution chain, the explicit switch, the stored default and
the company's display configuration, and that it refuses all five for an actor who holds
nothing there.
"""

from __future__ import annotations

from billing_platform.db import tenant_scope

from identity.models import Company
from tests.api_support import actor_headers, grant
from tests.factories import build_company, build_user, seed_two_companies


async def test_a_clerk_can_list_open_and_default_the_company_they_work_in(
    client, session, tenant_a, tenant_b
):
    main, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        other = build_company(tenant_id=tenant_a, code="AAA", display_name="Aardvark Ltd")
        clerk = build_user(tenant_id=tenant_a, email="clerk@example.test")
        session.add_all([other, clerk])
        await session.commit()
        other_id, clerk_id = other.id, clerk.id
    # An invoice clerk at company scope: no `company.read` anywhere.
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=clerk_id,
        grants=[grant(["invoice.create"], scope_type="company", scope_id=main)],
    )
    assert (await client.get("/v1/companies", headers=headers)).status_code == 403

    # The switcher lists their one company, and not the alphabetically first one.
    listed = (await client.get("/v1/session/companies", headers=headers)).json()
    assert [item["id"] for item in listed["items"]] == [str(main)]

    # The chain opens it: rule 4 among the companies they may work in, not the ones they
    # may describe — so it agrees with the list rather than contradicting it.
    body = (await client.get("/v1/session", headers=headers)).json()
    assert (body["selected_source"], body["company"]["id"]) == ("first", str(main))
    assert body["company"]["display_name"] == "Alpha Ltd"

    # And an explicit switch to the same company is honoured, not refused.
    explicit = await client.get(f"/v1/session?company_id={main}", headers=headers)
    assert explicit.status_code == 200, explicit.text
    assert (explicit.json()["selected_source"], explicit.json()["company"]["id"]) == (
        "explicit",
        str(main),
    )

    # The company's formatting is readable, because they have to render its figures the way
    # the company states them (CLAUDE.md §4) — it is not a company detail.
    display = await client.get(f"/v1/companies/{main}/display-config", headers=headers)
    assert display.status_code == 200, display.text
    assert display.json()["digit_grouping"] == "indian"
    # The company's own details stay behind `company.read`.
    assert (await client.get(f"/v1/companies/{main}", headers=headers)).status_code == 403

    # "Set as my default" accepts it, by the same rule the chain applies.
    stored = await client.patch(
        "/v1/session/preferences", headers=headers, json={"default_company_id": str(main)}
    )
    assert stored.status_code == 200, stored.text
    assert (await client.get("/v1/session", headers=headers)).json()["selected_source"] == "default"

    # Everything they hold nothing in is refused, in the same places — and a company in
    # another tenant is refused identically to one in this tenant they hold nothing in,
    # since the authority check runs before the row is looked up.
    for company_id in (other_id, foreign):
        assert str(company_id) not in {item["id"] for item in listed["items"]}
        assert (
            await client.get(f"/v1/session?company_id={company_id}", headers=headers)
        ).status_code == 403
        assert (
            await client.get(f"/v1/companies/{company_id}/display-config", headers=headers)
        ).status_code == 403
        assert (
            await client.patch(
                "/v1/session/preferences",
                headers=headers,
                json={"default_company_id": str(company_id)},
            )
        ).status_code == 422


async def test_an_actor_with_no_authority_reaches_no_company_context(
    client, session, tenant_a, tenant_b
):
    main, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        stranger = build_user(tenant_id=tenant_a, email="stranger@example.test")
        session.add(stranger)
        await session.commit()
        stranger_id = stranger.id
    headers = actor_headers(tenant_id=tenant_a, user_id=stranger_id)
    assert (await client.get("/v1/session/companies", headers=headers)).json()["items"] == []
    assert (await client.get("/v1/session", headers=headers)).json()["selected_source"] == "none"
    assert (await client.get(f"/v1/session?company_id={main}", headers=headers)).status_code == 403
    assert (
        await client.get(f"/v1/companies/{main}/display-config", headers=headers)
    ).status_code == 403
    with tenant_scope(tenant_a):
        # Nothing was created or changed by any of those refusals.
        assert (await session.get(Company, main)).status == "active"
