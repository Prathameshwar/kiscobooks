"""Signed counterparty dealer licences remain bound to party, premises and date."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT
from test_sources_custom_artifacts import source

from vouchers.domain.regulatory import require_dealer_licence, required_dealer_form
from vouchers.tasks.regulatory import effective_dealer_licence


@pytest.mark.parametrize(
    ("operation", "licence_class", "form"),
    [
        ("RETAIL", "OTHER_THAN_C_C1_X", "20"),
        ("RETAIL", "C_C1_EXCLUDING_X", "21"),
        ("WHOLESALE", "OTHER_THAN_C_C1_X", "20B"),
        ("WHOLESALE", "C_C1_EXCLUDING_X", "21B"),
    ],
)
def test_dealer_form_matrix(operation, licence_class, form):
    assert required_dealer_form(operation, licence_class) == form


def test_schedule_x_dealer_form_is_unavailable():
    with pytest.raises(ConflictError):
        required_dealer_form("WHOLESALE", "SCHEDULE_X")


async def test_accounting_dealer_licence_projection_and_closure(client, app):
    party_id, address_id, licence_id = uuid7(), uuid7(), uuid7()
    fact = {
        "entity_type": "party_drug_licence",
        "source_id": str(licence_id),
        "source_version": 1,
        "status": "ACTIVE",
        "facts": {
            "party_id": str(party_id),
            "address_id": str(address_id),
            "licence_form": "21B",
            "licence_number": "MH-21B-001",
            "valid_from": "2090-01-01",
            "valid_to": None,
            "source_sha256": "a" * 64,
            "reviewed_by": str(uuid7()),
            "reviewed_at": "2090-01-01T00:00:00Z",
        },
    }
    assert (await source(client, app, issuer="catalog", masters=[fact])).status_code == 422
    accepted = await source(client, app, issuer="accounting", masters=[fact])
    assert accepted.status_code == 200, accepted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            selected = await effective_dealer_licence(
                db,
                COMPANY,
                party_id,
                address_id,
                "WHOLESALE",
                "C_C1_EXCLUDING_X",
                dt.date(2090, 1, 1),
            )
            assert selected is not None and selected.licence_id == licence_id
            assert (
                require_dealer_licence(
                    selected,
                    party_id=party_id,
                    address_id=address_id,
                    operation="WHOLESALE",
                    licence_class="C_C1_EXCLUDING_X",
                    supply_date=dt.date(2090, 1, 1),
                )
                == selected
            )
            with pytest.raises(ConflictError):
                require_dealer_licence(
                    selected,
                    party_id=party_id,
                    address_id=uuid7(),
                    operation="WHOLESALE",
                    licence_class="C_C1_EXCLUDING_X",
                    supply_date=dt.date(2090, 1, 1),
                )
            assert (
                await effective_dealer_licence(
                    db,
                    COMPANY,
                    party_id,
                    address_id,
                    "RETAIL",
                    "C_C1_EXCLUDING_X",
                    dt.date(2090, 1, 1),
                )
                is None
            )
    closed = fact | {
        "source_version": 2,
        "facts": fact["facts"] | {"valid_to": "2090-12-31"},
    }
    assert (await source(client, app, issuer="accounting", masters=[closed])).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            assert (
                await effective_dealer_licence(
                    db,
                    COMPANY,
                    party_id,
                    address_id,
                    "WHOLESALE",
                    "C_C1_EXCLUDING_X",
                    dt.date(2091, 1, 1),
                )
                is None
            )
    altered = closed | {
        "source_version": 3,
        "facts": closed["facts"] | {"licence_number": "CHANGED"},
    }
    assert (await source(client, app, issuer="accounting", masters=[altered])).status_code == 409
