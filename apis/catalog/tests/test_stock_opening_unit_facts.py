"""Native opening conversions use the same owner scope and field policies as stock."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.gateway import decode_actor_context
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.stock_facts import StockFenceRequest

from catalog.models import InventoryProfileTemplateRevision, Item, ProductFamily
from catalog.models.product_definitions import ItemUnitRevision
from catalog.models.tax import ItemInventoryProfile
from catalog.tasks.stock_sources import PROFILE_FIELDS, build
from tests.conftest import ACTOR_SECRET
from tests.tax_factories import seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_classification_api import setup_source
from tests.source_factories import all_facts
from tests.unit_integrity_factories import binding_body, latest_revision, new_unit

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("mode", ["FIXED", "MEASURED"])
async def test_builder_pins_requested_unit_revision_and_refuses_wrong_scope_and_date(
    client, factory, tenant_a, mode
):
    root, _, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await setup_source(
        factory, tenant_a, company, ids["actor_user"], version=3,
        facts=tuple(row for row in all_facts(company, ids["actor_user"]) if row.kind != "field_policy"),
    )
    current = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=[*sorted(CATALOG_PERMISSIONS), "accounting.stock.read"],
    )
    requested_revision = ids["item_unit_revision"]
    if mode == "MEASURED":
        alternate = await new_unit(client, root, current, "COUNTED_PACK")
        response = await client.post(
            root + f"/items/{ids['item']}/unit-bindings",
            headers=command_headers(current),
            json=binding_body(
                alternate,
                role="MEASURED",
                conversion_mode="MEASURED",
                numerator=None,
                denominator=None,
                secondary_unit_id=str(ids["unit_of_measure"]),
                nominal_ratio="12",
            ),
        )
        assert response.status_code == 200, response.text
        created = await latest_revision(client, root, current, ids["item"], "ALT")
        requested_revision = uuid.UUID(created["id"])
    initialized = await client.post(
        root + "/warehouse-configuration/bootstrap", json={}, headers=command_headers(current)
    )
    assert initialized.status_code == 201, initialized.text
    configuration = (await client.get(root + "/warehouse-configuration", headers=current)).json()
    actor = decode_actor_context(
        current["x-actor-context"], current["x-actor-signature"], ACTOR_SECRET.encode()
    )
    # build() is the internal facts builder; request authentication is tested at
    # the signed transport boundary, before this function is entered.
    request = StockFenceRequest(
        purpose="PREVIEW",
        tenant_id=tenant_a,
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
        stock_date=dt.date(2090, 1, 1),
        content_hash="b" * 64,
        item_ids=(ids["item"],),
        warehouse_ids=(configuration["main_warehouse_id"],),
        opening_unit_revision_ids=(requested_revision,),
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            product = await db.get(Item, ids["item"])
            family = await db.get(ProductFamily, ids["product_family"])
            template = await db.get(
                InventoryProfileTemplateRevision, ids["inventory_profile_template_revision"]
            )
            product.status = family.status = "ACTIVE"
            db.add(
                ItemInventoryProfile(
                    tenant_id=tenant_a,
                    company_id=company,
                    item_id=product.id,
                    base_unit_id=product.base_unit_id,
                    template_revision_id=template.id,
                    **{key: getattr(template, key) for key in PROFILE_FIELDS},
                )
            )
        async with factory.begin() as db:
            facts = await build(db, actor, request, 1)
            proof = facts.items[0].opening_units[0]
            assert proof.revision_id == requested_revision
            assert proof.conversion_mode == mode
            assert proof.numerator == (1 if mode == "FIXED" else None)
            assert proof.denominator == (1 if mode == "FIXED" else None)
            alternate_request = request.model_copy(
                update={
                    "opening_unit_revision_ids": (),
                    "quantity_unit_revision_ids": (requested_revision,),
                }
            )
            quantity = await build(db, actor, alternate_request, 1)
            quantity_proof = quantity.items[0].quantity_units[0]
            assert quantity_proof.revision_id == requested_revision
            assert quantity_proof.conversion_mode == mode
            assert quantity_proof.numerator == ("1" if mode == "FIXED" else None)
            assert quantity_proof.denominator == ("1" if mode == "FIXED" else None)
        async with factory.begin() as db:
            with pytest.raises(ConflictError, match="unavailable"):
                await build(
                    db,
                    actor,
                    request.model_copy(update={"opening_unit_revision_ids": (uuid7(),)}),
                    1,
                )
        async with factory.begin() as db:
            revision = await db.scalar(
                select(ItemUnitRevision).where(ItemUnitRevision.id == ids["item_unit_revision"])
            )
            revision.valid_to = dt.date(2090, 1, 1)
        async with factory.begin() as db:
            with pytest.raises(ConflictError, match="base-unit revision"):
                await build(
                    db, actor, request.model_copy(update={"stock_date": dt.date(2090, 1, 2)}), 1
                )
