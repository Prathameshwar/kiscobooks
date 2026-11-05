"""Regression coverage across unit authoring, activation and quantity consumers."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.bulk_files import Cell
from billing_platform.db import tenant_scope
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ItemBarcode, ItemUnitRevision, UnitOfMeasure
from catalog.schemas.product_authoring import UnitBindingInput
from catalog.tasks import activation
from catalog.tasks.bulk_inputs import cell_value
from tests.test_commercial_api import command_headers
from tests.test_unit_api import access, seed_context
from tests.unit_integrity_factories import (
    binding_body,
    latest_revision,
    new_unit,
    serial_units,
    setup_units,
)

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("global_first", [True, False])
async def test_canonical_and_product_definitions_cannot_disagree(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    global_first: bool,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    base = (await client.get(path, headers=auth)).json()["base_unit_id"]
    dozen = await new_unit(client, root, auth, "DOZEN")
    canonical = {
        "from_unit_id": base,
        "canonical_unit_id": base,
        "numerator": "1",
        "denominator": "1",
    }
    result = await client.post(
        root + "/unit-conversions", headers=command_headers(auth), json=canonical
    )
    assert result.status_code == 201, result.text
    alternate = {**canonical, "from_unit_id": dozen, "numerator": "12"}
    if global_first:
        result = await client.post(
            root + "/unit-conversions", headers=command_headers(auth), json=alternate
        )
        assert result.status_code == 201, result.text
    result = await client.post(
        path + "/unit-bindings",
        headers=command_headers(auth),
        json=binding_body(dozen, numerator=10),
    )
    assert result.status_code == (409 if global_first else 200), result.text
    if global_first:
        result = await client.post(
            path + "/unit-bindings", headers=command_headers(auth), json=binding_body(dozen)
        )
        assert result.status_code == 200, result.text
    else:
        result = await client.post(
            root + "/unit-conversions", headers=command_headers(auth), json=alternate
        )
        assert result.status_code == 409, result.text
        result = await client.post(
            root + "/unit-conversions",
            headers=command_headers(auth),
            json={**alternate, "numerator": "10"},
        )
        assert result.status_code == 201, result.text
    revision = await latest_revision(client, root, auth, ids["item"], "ALT")
    converted = await client.post(
        root + "/units/convert",
        headers=auth,
        json={"from_unit_id": dozen, "to_unit_id": base, "quantity": "1"},
    )
    product = await client.post(
        path + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [{"unit_revision_id": revision["id"], "quantity": "1"}],
        },
    )
    assert converted.status_code == product.status_code == 200
    assert converted.json()["quantity"] == product.json()["base_quantity"]


async def test_measured_identity_is_rejected_atomically(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    before = (await client.get(path, headers=auth)).json()
    result = await client.post(
        path + "/unit-bindings",
        headers=command_headers(auth),
        json=binding_body(
            before["base_unit_id"],
            role="MEASURED",
            conversion_mode="MEASURED",
            numerator=None,
            denominator=None,
            secondary_unit_id=before["base_unit_id"],
            nominal_ratio="1",
        ),
    )
    assert result.status_code == 422, result.text
    assert (await client.get(path, headers=auth)).json() == before


async def test_product_ratio_strings_and_integer_retry_preserve_exact_identity(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    item = (await client.get(path, headers=auth)).json()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            base = await db.get(UnitOfMeasure, uuid.UUID(item["base_unit_id"]))
            revision = await db.get(ItemUnitRevision, ids["item_unit_revision"])
            assert base is not None and revision is not None
            base.decimal_places, base.quantity_increment = 4, Decimal("0.0001")
            (
                revision.quantity_decimal_places,
                revision.quantity_increment,
                revision.fractional_entry,
            ) = 4, Decimal("0.0001"), True
    big = await new_unit(client, root, auth, "BIG", decimals=4)
    body = binding_body(
        big,
        numerator="9007199254740993",
        denominator="1",
        quantity_decimal_places=4,
        quantity_increment="0.0001",
        fractional_entry=True,
    )
    write = command_headers(auth)
    result = await client.post(path + "/unit-bindings", headers=write, json=body)
    assert result.status_code == 200, result.text
    retry = await client.post(
        path + "/unit-bindings",
        headers=write,
        json={**body, "numerator": 9007199254740993, "denominator": 1},
    )
    assert retry.status_code == 200 and retry.headers["Idempotency-Replayed"] == "true", retry.text
    persisted = await latest_revision(client, root, auth, ids["item"], "ALT")
    assert persisted["numerator"] == "9007199254740993"
    assert persisted["denominator"] == "1"
    schema = UnitBindingInput.model_json_schema()
    with pytest.raises(ValueError, match="text cells"):
        cell_value(
            Cell("9007199254740992", "n"),
            schema["properties"]["numerator"],
            schema.get("$defs", {}),
        )

    from functools import partial

    from tests import bulk_factories
    from tests.test_bulk_products_prices import reviewed_commit

    monkeypatch.setattr(bulk_factories, "proofs", partial(bulk_factories.proofs, version=3))

    company = uuid.UUID(root.rsplit("/", 1)[1])
    job_id = await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        ids["actor_user"],
        auth,
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "ratio",
                    "change_set": "ratio",
                    "resource": "item",
                    "action": "REVISE_UNIT",
                    "target": {"id": str(ids["item"])},
                    "data": {
                        **body,
                        "expected_version": 2,
                        "binding_id": persisted["binding_id"],
                        "valid_from": "2091-01-01",
                        "numerator": "9007199254740995",
                    },
                }
            ],
        },
    )
    records_url = root + f"/bulk-jobs/{job_id}/records"
    listed = await client.get(records_url, headers=auth)
    assert listed.status_code == 200, listed.text
    record_id = listed.json()["items"][0]["id"]
    preview = await client.get(records_url + "/" + record_id, headers=auth)
    assert preview.status_code == 200, preview.text
    changed = [
        change["after"]
        for change in preview.json()["changes"]
        if change["resource"] == "item_unit_revision" and change["before"] is None
    ]
    assert len(changed) == 1 and changed[0]["numerator"] == "9007199254740995"
    assert changed[0]["denominator"] == "1"
    current = await latest_revision(client, root, auth, ids["item"], "ALT")
    assert current["numerator"] == "9007199254740995"


async def test_serial_unit_authoring_rejects_future_fractional_base(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await serial_units(factory, tenant_a)
    # Exercise the fractional serial rule on an unreferenced binding. The shared
    # seed includes a barcode, whose separate immutable-binding guard runs first.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            barcode = await db.get(ItemBarcode, ids["item_barcode"])
            assert barcode is not None
            await db.delete(barcode)
    path = root + f"/items/{ids['item']}"
    result = await client.post(
        path + "/unit-revisions",
        headers=command_headers(auth),
        json=binding_body(
            str(ids["unit_of_measure"]),
            binding_id=str(ids["item_unit_binding"]),
            code="BASE",
            role="BASE",
            numerator=1,
            quantity_decimal_places=1,
            quantity_increment="0.5",
            fractional_entry=True,
            valid_from="2091-01-01",
        ),
    )
    assert result.status_code == 422, result.text


@pytest.mark.parametrize("consumer", ["activation", "quantity", "pricing"])
async def test_legacy_fractional_serial_rules_fail_closed(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    consumer: str,
) -> None:
    root, auth, ids = await serial_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            previous = await db.get(ItemUnitRevision, ids["item_unit_revision"])
            assert previous is not None
            previous.valid_to = dt.date(2090, 12, 31)
            future = ItemUnitRevision(
                tenant_id=tenant_a,
                company_id=uuid.UUID(root.rsplit("/", 1)[1]),
                binding_id=previous.binding_id,
                revision=2,
                valid_from=dt.date(2091, 1, 1),
                conversion_mode="FIXED",
                numerator=1,
                denominator=1,
                quantity_decimal_places=1,
                quantity_increment="0.5",
                fractional_entry=True,
            )
            db.add(future)
            await db.flush()
            revision_id = str(future.id)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    if consumer == "activation":
        result = await client.post(
            path + "/activation-preview", headers=auth, json={"as_of": "2090-01-01"}
        )
        assert result.status_code == 200 and not result.json()["eligible"], result.text
        assert "integer_serial_base_quantity" in result.json()["missing"]
    else:
        body: dict[str, Any] = {"as_of": "2091-01-01"}
        if consumer == "quantity":
            route = path + "/quantity-preview"
            body["components"] = [{"unit_revision_id": revision_id, "quantity": "1.5"}]
        else:
            route = root + "/prices/resolve"
            body.update(
                item_id=str(ids["item"]),
                unit_revision_id=revision_id,
                quantity="1.5",
                currency="INR",
            )
        result = await client.post(route, headers=auth, json=body)
        assert result.status_code == 422 and "serial" in result.text, result.text


async def test_composed_ratio_keeps_exact_representable_quantity(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid.uuid4(), uuid.uuid4()
    await seed_context(factory, tenant_a, company, user)
    root = f"/v1/companies/{company}"
    write = access(tenant_a, company, user, "unit.manage")
    read = access(tenant_a, company, user, "unit.read")
    canonical, source, target = [
        await new_unit(client, root, write, name, decimals=4) for name in ("ROOT", "LARGE", "SMALL")
    ]
    for unit, numerator, denominator in (
        (canonical, "1", "1"),
        (source, "1000000000000000", "1"),
        (target, "1", "9500"),
    ):
        result = await client.post(
            root + "/unit-conversions",
            headers=command_headers(write),
            json={
                "from_unit_id": unit,
                "canonical_unit_id": canonical,
                "numerator": numerator,
                "denominator": denominator,
            },
        )
        assert result.status_code == 201, result.text
    result = await client.post(
        root + "/units/convert",
        headers=read,
        json={"from_unit_id": source, "to_unit_id": target, "quantity": "0.0001"},
    )
    assert (
        result.status_code == 200 and result.json()["quantity"] == "950000000000000.0000"
    ), result.text

    for left, right, quantity, expected in (
        (source, target, "0", 200),
        (source, target, "0.0002", 422),
        (target, source, "1", 422),
    ):
        result = await client.post(
            root + "/units/convert",
            headers=read,
            json={"from_unit_id": left, "to_unit_id": right, "quantity": quantity},
        )
        assert result.status_code == expected, result.text
