"""B24: stock facts for a purchase bill carry each item's purchase GST bundle, by identity."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.gateway import decode_actor_context
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.stock_facts import StockFenceRequest

from catalog.models import InventoryProfileTemplateRevision, Item, ProductFamily
from catalog.models.tax import CatalogTaxBinding, ItemInventoryProfile, TaxClassification
from catalog.tasks.stock_sources import PROFILE_FIELDS, build
from tests.conftest import ACTOR_SECRET
from tests.source_factories import all_facts
from tests.tax_factories import DATE, seed_tax
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def stocked(client, factory, tenant):
    root, _, ids = await seed_tax(factory, tenant)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await setup_source(
        factory,
        tenant,
        company,
        ids["actor_user"],
        version=3,
        facts=tuple(
            row for row in all_facts(company, ids["actor_user"]) if row.kind != "field_policy"
        ),
    )
    current = headers(
        company,
        tenant=tenant,
        user=ids["actor_user"],
        permission=[*sorted(CATALOG_PERMISSIONS), "accounting.stock.read"],
    )
    initialized = await client.post(
        root + "/warehouse-configuration/bootstrap", json={}, headers=command_headers(current)
    )
    assert initialized.status_code == 201, initialized.text
    configuration = (await client.get(root + "/warehouse-configuration", headers=current)).json()
    actor = decode_actor_context(
        current["x-actor-context"], current["x-actor-signature"], ACTOR_SECRET.encode()
    )
    request = StockFenceRequest(
        purpose="PREVIEW",
        tenant_id=tenant,
        company_id=company,
        execution_id=uuid7(),
        actor_user_id=ids["actor_user"],
        authority=DelegatedAuthority(
            actor_context=current["x-actor-context"],
            actor_signature=current["x-actor-signature"],
            company_context="builder-test-only",
            company_signature="a" * 64,
        ),
        authority_expires_at=utcnow() + dt.timedelta(seconds=45),
        stock_date=DATE,
        content_hash="b" * 64,
        item_ids=(ids["item"],),
        warehouse_ids=(configuration["main_warehouse_id"],),
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            product = await db.get(Item, ids["item"])
            family = await db.get(ProductFamily, ids["product_family"])
            template = await db.get(
                InventoryProfileTemplateRevision, ids["inventory_profile_template_revision"]
            )
            product.status = family.status = "ACTIVE"
            db.add(
                ItemInventoryProfile(
                    tenant_id=tenant,
                    company_id=company,
                    item_id=product.id,
                    base_unit_id=product.base_unit_id,
                    template_revision_id=template.id,
                    **{key: getattr(template, key) for key in PROFILE_FIELDS},
                )
            )
    return actor, request, ids


async def test_stock_facts_preserve_receiving_warehouse_address_and_tax_reference(
    client, factory, tenant_a
):
    from catalog.models.warehouses import Warehouse
    from tests.commercial_factories import reference_data

    await reference_data(factory)
    actor, request, _ = await stocked(client, factory, tenant_a)
    registration = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            warehouse = await db.get(Warehouse, request.warehouse_ids[0])
            warehouse.country_code = "IN"
            warehouse.state_code = "IN-MH"
            warehouse.tax_registration_id = registration
            warehouse.timezone = "Asia/Kolkata"
            warehouse.address_line1 = "Receiving warehouse address"
        async with factory.begin() as db:
            facts = await build(db, actor, request, 1)
    fact = next(row for row in facts.warehouses if row.warehouse_id == request.warehouse_ids[0])
    assert fact.tax_registration_id == registration
    assert fact.country_code == "IN" and fact.state_code == "IN-MH"
    assert fact.timezone == "Asia/Kolkata"
    assert fact.address_line1 == "Receiving warehouse address"


async def test_a_purchase_bill_request_receives_the_items_purchase_gst_bundle(
    client, factory, tenant_a
):
    actor, request, ids = await stocked(client, factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            plain = await build(db, actor, request, 1)
            assert plain.items[0].purchase_tax is None
            assert "purchase_tax" not in plain.items[0].model_dump(mode="json")
            asked = await build(
                db, actor, request.model_copy(update={"include_purchase_tax": True}), 1
            )
            fact = asked.items[0].purchase_tax
            classification = await db.scalar(
                select(TaxClassification).where(TaxClassification.id == fact.classification_id)
            )
    assert fact is not None
    assert fact.code == classification.code
    assert fact.treatment == "TAXABLE"
    assert fact.rule_id is not None and fact.rule_version >= 1


async def test_an_item_without_a_complete_purchase_bundle_gets_none_not_a_guess(
    client, factory, tenant_a
):
    actor, request, ids = await stocked(client, factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            rule_binding = await db.scalar(
                select(CatalogTaxBinding).where(
                    CatalogTaxBinding.id == ids["binding_PURCHASE_RULE"]
                )
            )
            await db.delete(rule_binding)
        async with factory.begin() as db:
            asked = await build(
                db, actor, request.model_copy(update={"include_purchase_tax": True}), 1
            )
    assert asked.items[0].purchase_tax is None


async def test_a_print_request_receives_the_base_units_symbol_and_stock_never_does(
    client, factory, tenant_a
):
    from catalog.models.units import UnitOfMeasure

    actor, request, ids = await stocked(client, factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            plain = await build(db, actor, request, 1)
            labelled = await build(
                db, actor, request.model_copy(update={"include_labels": True}), 1
            )
            unit = await db.get(UnitOfMeasure, plain.items[0].base_unit_id)
    assert plain.items[0].base_unit_label is None
    assert "base_unit_label" not in plain.items[0].model_dump(mode="json")
    assert "include_labels" not in request.model_dump(mode="json")
    assert labelled.items[0].base_unit_label == unit.symbol


def test_a_unit_symbol_this_actor_may_not_read_is_withheld_not_refused():
    from types import SimpleNamespace

    from catalog.tasks.stock_sources import readable_label

    def context(readable):
        return SimpleNamespace(
            native=SimpleNamespace(fields={"symbol": None, "code": None}),
            readable=lambda values: readable,
        )

    unit = SimpleNamespace(symbol="kg", code="KGM")
    assert readable_label(context({"symbol", "code"}), unit, "symbol") == "kg"
    assert readable_label(context({"code"}), unit, "symbol") is None
    assert readable_label(context({"symbol"}), SimpleNamespace(symbol=""), "symbol") is None
