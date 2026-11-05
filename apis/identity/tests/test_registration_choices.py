from __future__ import annotations

from billing_platform.db import unfiltered
from sqlalchemy import func, select

from identity.models import Country, State, Tenant, User

pytest_plugins = ["tests.test_platform_setup"]


async def test_registration_exposes_only_active_public_regions_without_writes(
    setup_app, client, factory
):
    async with factory() as db, db.begin():
        db.add(
            State(
                code="IN-MH",
                country_code="IN",
                name="Maharashtra",
                subdivision_type="State",
                is_active=True,
            )
        )
        db.add(
            State(
                code="IN-DL",
                country_code="IN",
                name="Delhi",
                subdivision_type="Union territory",
                is_active=False,
            )
        )
    response = await client.get("/v1/registration/options")
    assert response.status_code == 200
    assert response.json() == {
        "countries": [{"code": "IN", "name": "India"}],
        "states": [{"code": "IN-MH", "name": "Maharashtra", "country_code": "IN"}],
    }
    async with factory() as db:
        with unfiltered():
            assert await db.scalar(select(func.count()).select_from(User)) == 0
            assert await db.scalar(select(func.count()).select_from(Tenant)) == 0


async def test_registration_choices_reject_arbitrary_parameters(setup_app, client):
    response = await client.get("/v1/registration/options?tenant_id=anything")
    assert response.status_code == 422


async def test_inactive_country_hides_its_states_and_anonymous_reads_are_limited(
    setup_app, client, factory
):
    async with factory() as db, db.begin():
        country = await db.get(Country, "IN")
        country.is_active = False
        db.add(
            State(
                code="IN-MH",
                country_code="IN",
                name="Maharashtra",
                subdivision_type="State",
                is_active=True,
            )
        )
    response = await client.get("/v1/registration/options")
    assert response.status_code == 200 and response.json() == {"countries": [], "states": []}
    assert response.headers["Cache-Control"] == "no-store"
    app, _, _ = setup_app
    from unittest.mock import Mock

    app.state.auth_limiter = Mock()
    app.state.auth_limiter.allow.return_value = False
    response = await client.get("/v1/registration/options")
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"
