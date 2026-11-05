"""Exercise native Catalog creation, pricing and activation inside the import savepoint."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import select

from catalog.models.pricing import ItemPriceDraft
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item
from catalog.schemas.configuration import EffectiveQuery
from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.schemas.simple_products import SimpleProductCreate
from catalog.tasks.bulk_registry import OPERATIONS, Runtime, reviewed_product_call
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_resolution import resolve
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import row


async def validate_product(
    runtime: Runtime, body: SimpleCreationInput, progress: dict[str, Any], key: str
) -> None:
    async def call(
        resource: str, action: str, data: dict[str, Any], target: uuid.UUID | None = None
    ) -> dict[str, Any]:
        operation = OPERATIONS[resource, action]
        handler = (
            reviewed_product_call(activate=True, reuse_locked_review=True)
            if (resource, action) == ("item", "ACTIVATE")
            else operation.call
        )
        return await handler(
            runtime,
            operation.schema.model_validate(data),
            target,
            key + ":" + resource + ":" + action + ":" + str(target or ""),
        )

    native = SimpleProductCreate.model_validate(progress["create"])
    created = await call("simple_product", "CREATE", native.model_dump(mode="json"))
    item_id = uuid.UUID(created["id"])
    today = dt.date.fromisoformat(progress["today"])
    drafts = [uuid.UUID(value) for value in created.get("price_draft_ids", [])]
    if body.mrp is not None:
        unit = await runtime.db.scalar(
            select(ItemUnitRevision)
            .join(ItemUnitBinding, ItemUnitRevision.binding_id == ItemUnitBinding.id)
            .where(
                ItemUnitBinding.company_id == runtime.company,
                ItemUnitBinding.item_id == item_id,
                ItemUnitBinding.usage_role == "BASE",
                ItemUnitRevision.valid_from <= today,
                ItemUnitRevision.valid_to.is_(None),
            )
        )
        if unit is None:
            raise ConflictError("The product base unit is unavailable")
        configuration = await resolve(
            runtime.db,
            runtime.actor,
            runtime.company,
            EffectiveQuery(as_of=today, kind=body.kind, item_id=item_id),
        )
        data = {
            "item_id": str(item_id),
            "unit_revision_id": str(unit.id),
            "currency": progress["currency"],
            "valid_from": progress["today"],
            "expected_generation": configuration.policy_generation,
            "expected_source_version": configuration.source_version,
        }
        if drafts:
            draft = await runtime.db.get(ItemPriceDraft, drafts[0])
            assert draft is not None
            numeric_id = str(draft.numeric_revision_id)
        else:
            numeric = await call(
                "item_price_numeric_revision",
                "CREATE",
                data | {"price_decimal_places": progress["price_places"]},
            )
            numeric_id = numeric["id"]
            configuration = await resolve(
                runtime.db,
                runtime.actor,
                runtime.company,
                EffectiveQuery(as_of=today, kind=body.kind, item_id=item_id),
            )
            data["expected_generation"] = configuration.policy_generation
            data["expected_source_version"] = configuration.source_version
        await call(
            "item_mrp",
            "CREATE",
            data
            | {
                "numeric_revision_id": numeric_id,
                "amount": str(body.mrp),
                "price_basis_quantity": "1",
                "jurisdiction": progress["jurisdiction"],
                "tax_basis": "INCLUSIVE",
                "source_reference": "Simple product import validation",
            },
        )
    access = ConfigurationAccess(runtime.db, runtime.actor, runtime.company)
    for draft_id in drafts:
        # These drafts were just created in this validation savepoint. Publication
        # runs full readiness/history checks itself; a preview would repeat them.
        value = await row(access, ItemPriceDraft, draft_id)
        state = await policy_state(runtime.db, runtime.actor, runtime.company)
        context = await access.context(ItemPriceDraft)
        await call(
            "item_price_draft",
            "PUBLISH",
            {
                "expected_version": value.row_version,
                "expected_generation": state.generation if state else 1,
                "expected_source_version": context.source_version,
            },
            draft_id,
        )
    item = await runtime.db.get(Item, item_id)
    assert item is not None
    await call(
        "item",
        "ACTIVATE",
        {"as_of": progress["today"], "expected_version": item.row_version},
        item_id,
    )
