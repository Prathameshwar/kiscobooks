"""HTTP tests for the tax-registration write rules (docs/tax-accounting-plan.md Phase 1).

* GSTIN check character and state prefix are enforced at the boundary (1.1);
* ``regime``, ``number``, ``jurisdiction_code`` and ``valid_from`` are immutable after
  create — 422 for every actor, including a tenant-wide manager (1.2);
* a regular GSTIN and a TDS-deductor registration coexist in one state (1.3);
* at most one ``is_primary`` per ``(tax_system, jurisdiction)`` on any date (1.4);
* the amendment audit event carries the changed-field set, with PII redacted (1.5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from billing_platform.db import tenant_scope
from billing_platform.db.tenant_context import unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyTaxRegistration, Outbox
from tests.api_support import actor_headers, grant
from tests.factories import build_company, seed_two_companies

pytestmark = pytest.mark.asyncio

MANAGE = "company.tax_registration.manage"
REGULAR_MH = "27AAAPA1234A1ZT"


def _gstin(first14: str) -> str:
    """Append a mod-36 check character, computed independently of the platform."""
    total = 0
    for index, char in enumerate(first14):
        quotient, remainder = divmod(int(char, 36) * (2 if index % 2 else 1), 36)
        total += quotient + remainder
    return first14 + "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[(36 - total % 36) % 36]


TDS_MH = _gstin("27MUMA12345B1D")
TCS_MH = _gstin("27AAAPA1234A1C")


@dataclass
class World:
    tenant: uuid.UUID
    company: uuid.UUID
    other_company: uuid.UUID
    actor: uuid.UUID

    def headers(self, *permissions: str, company: uuid.UUID | None = None) -> dict[str, str]:
        scoped = (
            grant(list(permissions))
            if company is None
            else grant(list(permissions), scope_type="company", scope_id=company)
        )
        return actor_headers(tenant_id=self.tenant, user_id=self.actor, grants=[scoped])

    def path(self, company: uuid.UUID | None = None) -> str:
        return f"/v1/companies/{company or self.company}/tax-registrations"


@pytest_asyncio.fixture
async def world(session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID) -> World:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    other = uuid7()
    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, company_id=other, code="SECOND"))
        await session.commit()
    return World(tenant_a, company, other, uuid7())


def _body(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "tax_system": "gst_in",
        "regime": "regular",
        "number": REGULAR_MH,
        "jurisdiction_code": "MH",
        "valid_from": "2026-04-01",
        "is_primary": True,
    }
    body.update(over)
    return body


async def _create(client: httpx.AsyncClient, world: World, **over: object) -> dict[str, object]:
    response = await client.post(world.path(), json=_body(**over), headers=world.headers(MANAGE))
    assert response.status_code == 201, response.text
    created: dict[str, object] = response.json()
    return created


async def _amended_audits(session: AsyncSession, world: World) -> list[Outbox]:
    with tenant_scope(world.tenant):
        rows = await session.scalars(select(Outbox))
        return [r for r in rows if r.payload.get("action") == "company.tax_registration_amended"]


# --- 1.1 checksum and state prefix -------------------------------------------------


async def test_a_gstin_with_a_wrong_check_character_is_422(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.post(
        world.path(), json=_body(number="27AAAPA1234A1Z5"), headers=world.headers(MANAGE)
    )

    assert response.status_code == 422, response.text
    assert "check character" in response.text


async def test_a_gstin_from_another_state_is_422(client: httpx.AsyncClient, world: World) -> None:
    response = await client.post(
        world.path(), json=_body(number=_gstin("29AAAPA1234A1Z")), headers=world.headers(MANAGE)
    )

    assert response.status_code == 422, response.text
    assert "state prefix 29" in response.text


async def test_entity_code_zero_is_422(client: httpx.AsyncClient, world: World) -> None:
    response = await client.post(
        world.path(), json=_body(number=_gstin("27AAAPA1234A0Z")), headers=world.headers(MANAGE)
    )

    assert response.status_code == 422, response.text


# --- 1.3 / 1.4 coexistence and primary ---------------------------------------------


async def test_a_tds_deductor_registration_coexists_with_the_regular_one(
    client: httpx.AsyncClient, world: World
) -> None:
    """Same state, same start day: regression for the unique key that omitted the
    class (revision 0063)."""
    regular = await _create(client, world)

    deductor = await _create(client, world, regime="tds_deductor", number=TDS_MH, is_primary=False)

    assert deductor["number"] == TDS_MH
    assert regular["registration_class"] == "supplier"
    assert deductor["registration_class"] == "tds_deductor"


async def test_an_ecommerce_tcs_registration_coexists_with_the_regular_one(
    client: httpx.AsyncClient, world: World
) -> None:
    await _create(client, world)

    collector = await _create(
        client, world, regime="ecommerce_operator", number=TCS_MH, is_primary=False
    )

    assert collector["registration_class"] == "tcs_collector"


async def test_a_tcs_shaped_gstin_is_refused_for_a_regular_registration(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.post(
        world.path(), json=_body(number=TCS_MH), headers=world.headers(MANAGE)
    )

    assert response.status_code == 422, response.text


async def test_the_registration_class_cannot_be_chosen_by_the_client(
    client: httpx.AsyncClient, world: World
) -> None:
    """It is derived from the regime; accepting it would let a second supplier row
    dodge the overlap rule by calling itself a deductor."""
    response = await client.post(
        world.path(),
        json=_body(registration_class="tds_deductor"),
        headers=world.headers(MANAGE),
    )

    assert response.status_code == 422, response.text


async def test_two_regular_registrations_in_one_state_conflict(
    client: httpx.AsyncClient, world: World
) -> None:
    await _create(client, world)

    response = await client.post(
        world.path(),
        json=_body(number="27AAAPA1234A2ZS", valid_from="2026-06-01", is_primary=False),
        headers=world.headers(MANAGE),
    )

    assert response.status_code == 409, response.text


async def test_a_second_primary_in_one_state_conflicts_on_create(
    client: httpx.AsyncClient, world: World
) -> None:
    await _create(client, world)

    response = await client.post(
        world.path(),
        json=_body(regime="tds_deductor", number=TDS_MH, is_primary=True, valid_from="2026-05-01"),
        headers=world.headers(MANAGE),
    )

    assert response.status_code == 409, response.text
    assert "primary" in response.text


async def test_a_second_primary_in_one_state_conflicts_on_amend(
    client: httpx.AsyncClient, world: World
) -> None:
    await _create(client, world)
    deductor = await _create(
        client,
        world,
        regime="tds_deductor",
        number=TDS_MH,
        is_primary=False,
        valid_from="2026-05-01",
    )

    response = await client.patch(
        f"{world.path()}/{deductor['id']}", json={"is_primary": True}, headers=world.headers(MANAGE)
    )

    assert response.status_code == 409, response.text


# --- 1.2 immutability ------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("regime", "composition"),
        ("number", "27AAAPA1234A2ZS"),
        ("jurisdiction_code", "MH-X"),
        ("valid_from", "2026-05-01"),
    ],
)
async def test_changing_an_identity_field_is_422_and_leaves_no_trace(
    client: httpx.AsyncClient, session: AsyncSession, world: World, field: str, value: str
) -> None:
    """A tenant-wide manager is refused too: this is not a permission."""
    created = await _create(client, world)

    response = await client.patch(
        f"{world.path()}/{created['id']}", json={field: value}, headers=world.headers(MANAGE)
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "immutable_field"
    with tenant_scope(world.tenant):
        row = await session.get(CompanyTaxRegistration, uuid.UUID(str(created["id"])))
        assert row is not None
        await session.refresh(row)
    assert str(getattr(row, field)) == str(created[field])
    assert await _amended_audits(session, world) == []


async def test_closing_a_registration_is_allowed_and_audited_with_the_changed_fields(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    created = await _create(client, world)

    response = await client.patch(
        f"{world.path()}/{created['id']}",
        json={
            # Echoed unchanged: not an edit, not refused.
            "regime": "regular",
            "number": REGULAR_MH.lower(),
            "valid_to": "2026-09-30",
            "legal_name_on_registration": "Alpha Traders Private Limited",
        },
        headers=world.headers(MANAGE),
    )

    assert response.status_code == 200, response.text
    assert response.json()["valid_to"] == "2026-09-30"
    [event] = await _amended_audits(session, world)
    changes = event.payload["changes"]
    assert set(changes) == {"valid_to", "legal_name_on_registration"}
    assert changes["valid_to"] == {"from": None, "to": "2026-09-30"}
    # The legal name is outside identity's audit allowlist: name only, value redacted.
    assert changes["legal_name_on_registration"] == {"from": "[redacted]", "to": "[redacted]"}
    assert "Alpha Traders" not in str(event.payload)


async def test_a_no_op_amendment_emits_no_audit(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    created = await _create(client, world)

    response = await client.patch(
        f"{world.path()}/{created['id']}", json={"is_primary": True}, headers=world.headers(MANAGE)
    )

    assert response.status_code == 200, response.text
    assert await _amended_audits(session, world) == []


async def test_the_regime_change_route_is_close_then_reopen(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await _create(client, world, regime="composition")
    closed = await client.patch(
        f"{world.path()}/{created['id']}",
        json={"valid_to": "2026-09-30"},
        headers=world.headers(MANAGE),
    )
    assert closed.status_code == 200, closed.text

    reopened = await _create(client, world, regime="regular", valid_from="2026-10-01")

    assert reopened["regime"] == "regular"


# --- §7 per-endpoint authorization ---------------------------------------------------


async def test_amend_unauthenticated_is_401(client: httpx.AsyncClient, world: World) -> None:
    created = await _create(client, world)

    response = await client.patch(f"{world.path()}/{created['id']}", json={"valid_to": None})

    assert response.status_code == 401


async def test_amend_without_permission_is_403(client: httpx.AsyncClient, world: World) -> None:
    created = await _create(client, world)

    response = await client.patch(
        f"{world.path()}/{created['id']}",
        json={"valid_to": "2026-09-30"},
        headers=world.headers("company.read"),
    )

    assert response.status_code == 403


async def test_amend_in_another_company_is_403(client: httpx.AsyncClient, world: World) -> None:
    """A manager scoped to the other company holds the key but not the object."""
    created = await _create(client, world)

    response = await client.patch(
        f"{world.path()}/{created['id']}",
        json={"valid_to": "2026-09-30"},
        headers=world.headers(MANAGE, company=world.other_company),
    )

    assert response.status_code == 403


async def test_a_registration_cannot_be_amended_through_another_companys_path(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await _create(client, world)

    response = await client.patch(
        f"{world.path(world.other_company)}/{created['id']}",
        json={"valid_to": "2026-09-30"},
        headers=world.headers(MANAGE),
    )

    assert response.status_code == 404


async def test_create_in_another_company_is_403(client: httpx.AsyncClient, world: World) -> None:
    response = await client.post(
        world.path(), json=_body(), headers=world.headers(MANAGE, company=world.other_company)
    )

    assert response.status_code == 403
