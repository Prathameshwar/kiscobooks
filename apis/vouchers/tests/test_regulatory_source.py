"""Only Catalog can project reviewed dated food and medicine classifications."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT
from sqlalchemy import select
from test_sources_custom_artifacts import source

from vouchers.domain.regulatory import RegulatorySelection, require_supported_medicine
from vouchers.models.core import VoucherItemRegulatoryProjection
from vouchers.tasks.regulatory import effective


async def test_catalog_regulatory_history_is_owner_scoped_and_replay_safe(client, app):
    item_id = uuid7()
    classification_id = uuid7()
    fact = {
        "entity_type": "item_regulatory_classification",
        "source_id": str(classification_id),
        "source_version": 1,
        "status": "ACTIVE",
        "facts": {
            "item_id": str(item_id),
            "valid_from": "2090-01-01",
            "valid_to": None,
            "product_kind": "MEDICINE",
            "licence_class": "C_C1_EXCLUDING_X",
            "prescription_schedule": "H1",
            "source_sha256": "a" * 64,
            "reviewed_by": str(uuid7()),
            "reviewed_at": "2090-01-01T00:00:00Z",
        },
    }
    assert (await source(client, app, issuer="accounting", masters=[fact])).status_code == 422
    message = uuid7()
    accepted = await source(client, app, issuer="catalog", masters=[fact], message_id=message)
    assert accepted.status_code == 200, accepted.text
    replay = await source(client, app, issuer="catalog", masters=[fact], message_id=message)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            rows = list(
                await db.scalars(
                    select(VoucherItemRegulatoryProjection).where(
                        VoucherItemRegulatoryProjection.company_id == COMPANY,
                        VoucherItemRegulatoryProjection.classification_id == classification_id,
                    )
                )
            )
    assert len(rows) == 1
    assert rows[0].item_id == item_id
    assert rows[0].prescription_schedule == "H1"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            resolved = await effective(db, COMPANY, item_id, dt.date(2090, 1, 1))
            assert resolved is not None
            assert resolved.classification_id == classification_id
            assert (
                require_supported_medicine(
                    resolved, item_id=item_id, supply_date=dt.date(2090, 1, 1)
                )
                == resolved
            )
            assert await effective(db, COMPANY, item_id, dt.date(2089, 12, 31)) is None
    closed = fact | {
        "source_version": 2,
        "facts": fact["facts"] | {"valid_to": "2090-12-31"},
    }
    assert (await source(client, app, issuer="catalog", masters=[closed])).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            assert await effective(db, COMPANY, item_id, dt.date(2091, 1, 1)) is None
    rewritten = closed | {
        "source_version": 3,
        "facts": closed["facts"] | {"source_sha256": "b" * 64},
    }
    assert (await source(client, app, issuer="catalog", masters=[rewritten])).status_code == 409


def test_medicine_gate_rejects_missing_source_and_schedule_x():
    item_id = uuid7()
    with pytest.raises(ConflictError):
        require_supported_medicine(None, item_id=item_id, supply_date=dt.date(2090, 1, 1))
    selected = RegulatorySelection(
        classification_id=uuid7(),
        source_version=1,
        item_id=item_id,
        valid_from=dt.date(2090, 1, 1),
        valid_to=None,
        product_kind="MEDICINE",
        licence_class="SCHEDULE_X",
        prescription_schedule="X",
        source_sha256="a" * 64,
    )
    with pytest.raises(ConflictError):
        require_supported_medicine(selected, item_id=item_id, supply_date=dt.date(2090, 1, 1))


async def test_regulatory_source_rejects_missing_review_or_invalid_schedule(client, app):
    fact = {
        "entity_type": "item_regulatory_classification",
        "source_id": str(uuid7()),
        "source_version": 1,
        "status": "ACTIVE",
        "facts": {
            "item_id": str(uuid7()),
            "valid_from": "2090-01-01",
            "valid_to": None,
            "product_kind": "MEDICINE",
            "licence_class": "C_C1_EXCLUDING_X",
            "prescription_schedule": "H1",
            "source_sha256": "a" * 64,
            "reviewed_by": str(uuid7()),
            "reviewed_at": "2090-01-01T00:00:00Z",
        },
    }
    invalid = dict(fact["facts"])
    invalid["prescription_schedule"] = "X"
    assert (
        await source(client, app, issuer="catalog", masters=[fact | {"facts": invalid}])
    ).status_code == 422
    missing = dict(fact["facts"])
    missing.pop("reviewed_by")
    assert (
        await source(client, app, issuer="catalog", masters=[fact | {"facts": missing}])
    ).status_code == 422


async def test_food_category_projection_is_dated_and_immutable(client, app):
    item_id = uuid7()
    fact = {
        "entity_type": "item_regulatory_classification",
        "source_id": str(uuid7()),
        "source_version": 1,
        "status": "ACTIVE",
        "facts": {
            "item_id": str(item_id),
            "valid_from": "2090-01-01",
            "valid_to": None,
            "product_kind": "FOOD",
            "licence_class": None,
            "prescription_schedule": None,
            "food_category_code": "DAIRY.MILK",
            "source_sha256": "a" * 64,
            "reviewed_by": str(uuid7()),
            "reviewed_at": "2090-01-01T00:00:00Z",
        },
    }
    invalid = fact | {"facts": fact["facts"] | {"food_category_code": None}}
    assert (await source(client, app, issuer="catalog", masters=[invalid])).status_code == 422
    accepted = await source(client, app, issuer="catalog", masters=[fact])
    assert accepted.status_code == 200, accepted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            selected = await effective(db, COMPANY, item_id, dt.date(2090, 1, 1))
            assert selected is not None
            assert selected.product_kind == "FOOD"
            assert selected.food_category_code == "DAIRY.MILK"
    rewritten = fact | {
        "source_version": 2,
        "facts": fact["facts"] | {"food_category_code": "DAIRY.CURD"},
    }
    assert (await source(client, app, issuer="catalog", masters=[rewritten])).status_code == 409
