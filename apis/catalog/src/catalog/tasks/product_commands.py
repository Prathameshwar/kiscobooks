"""One current-authority transaction for native product aggregate edits."""

import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.classification import CatalogPolicyState
from catalog.models.products import Item, ProductFamily
from catalog.schemas.product_authoring import AuthoringResult
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import audit_change
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldWriteChecks, load_field_context
from catalog.tasks.policy_state import policy_state

if TYPE_CHECKING:
    from catalog.tasks.simple_products import ProductGuard


class ProductWork:
    def __init__(
        self,
        db: AsyncSession,
        actor: Actor,
        company: uuid.UUID,
        family: ProductFamily,
        item: Item | None,
        access: ConfigurationAccess,
    ) -> None:
        self.db, self.actor, self.company = db, actor, company
        self.family, self.item, self.access = family, item, access
        self.changed: dict[str, set[str]] = {}
        self.ids: list[uuid.UUID] = []

    async def record(self, row: Any, before: Mapping[str, Any], action: str = "create") -> None:
        fields = await self.access.write(row, before)
        if not fields:
            return
        entity = "catalog." + row.__tablename__
        self.changed.setdefault(entity, set()).update(fields)
        audit_change(
            self.db,
            self.actor,
            self.company,
            entity,
            row.id,
            action,
            fields,
            before=before,
            after=await self.access.values(row),
        )
        if row.id not in self.ids:
            self.ids.append(row.id)

    async def new(self, model: type[Any], **values: Any) -> Any:
        row = model(
            id=uuid7(),
            tenant_id=self.actor.tenant_id,
            company_id=self.company,
            created_by=self.actor.user_id,
            updated_by=self.actor.user_id,
            row_version=1,
            **values,
        )
        await self.record(row, {})
        return row

    async def retire_draft(self, row: Any) -> None:
        await self.access.require(row)
        before = await self.access.values(row)
        context = await self.access.context(type(row))
        context.assert_writable(
            frozenset(before),
            before=before,
            after={},
            checked=self.access.checks.setdefault(context.native.entity_type, FieldWriteChecks()),
        )
        self.changed.setdefault(context.native.entity_type, set()).update(before)
        audit_change(
            self.db,
            self.actor,
            self.company,
            context.native.entity_type,
            row.id,
            "update",
            frozenset(before),
            before=before,
            after={},
        )
        await self.db.delete(row)


Handler = Callable[[ProductWork, Any], Awaitable[None]]


async def execute(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    key: str,
    action: str,
    handler: Handler,
    *,
    item: bool = False,
    product_guard: "ProductGuard | None" = None,
) -> CommandResult[AuthoringResult]:
    entity = "catalog.item" if item else "catalog.product_family"
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        entity + "." + ("product_" if product_guard else "") + action,
        key,
        {
            "id": str(object_id),
            **(
                {
                    "product": str(product_guard.item_id),
                    "revision": product_guard.revision,
                    "authoring_version": product_guard.authoring_version,
                }
                if product_guard
                else {}
            ),
            "body": body.model_dump(
                mode="json",
                exclude={
                    field
                    for field in (
                        "accept_defaults",
                        "expected_default_item_version",
                    )
                    if getattr(body, field, None) is None
                },
            ),
            # Keep existing nonempty/omitted request fingerprints stable. An explicit
            # empty replacement is a new clear operation, distinct from omission.
            **(
                {"replace_empty_default_attributes": True}
                if "default_item_attributes" in body.model_fields_set
                and not getattr(body, "default_item_attributes", None)
                else {}
            ),
        },
    )
    state: CatalogPolicyState | None = None
    checks: dict[str, FieldWriteChecks] = {}

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal state
        actor.require_scope("item.read", target=ScopePath(company_id=company))
        if action == "create_variant":
            actor.require_scope("item.create", target=ScopePath(company_id=company))
        if action == "adopt_configuration":
            actor.require_scope("product_configuration.adopt", target=ScopePath(company_id=company))
        if action == "activate":
            actor.require_scope("item.activate", target=ScopePath(company_id=company))
        await load_field_context(db, actor, company, entity, permission="item.update")
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            if action in {"assign_categories", "activate"}:
                from billing_platform.errors import PermissionDeniedError

                from catalog.models.classification import CategoryScheme
                from catalog.models.product_definitions import FamilyCategory
                from catalog.schemas.product_authoring import (
                    CategoryAssignmentInput,
                    CategorySelection,
                )
                from catalog.tasks.category_membership import references

                access = ConfigurationAccess(db, actor, company)
                if action == "activate":
                    for model in (CategoryScheme, FamilyCategory):
                        dependency = await access.context(model)
                        if set(dependency.native.fields) - dependency.readable():
                            raise PermissionDeniedError(
                                "activation category dependencies are protected"
                            )
                original = (
                    [entry.model_dump() for entry in body.categories]
                    if isinstance(body, CategoryAssignmentInput)
                    else []
                )
                dependencies = [
                    CategorySelection.model_validate(row)
                    for row in receipt.get("category_dependencies", original)
                ]
                await references(access, dependencies, active=False)
            for name, fields in receipt["changed"].items():
                context = await load_field_context(db, actor, company, name)
                if name in checks:
                    checks[name].recheck(context)
                else:
                    assert_fields_writable(
                        frozenset(fields),
                        rules=context.rules(),
                        target=ScopePath(company_id=company),
                    )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert state is not None
        access = ConfigurationAccess(db, actor, company)
        access.checks = checks
        sku = await access.reference(Item, object_id) if item else None
        family = await access.reference(ProductFamily, sku.family_id if sku else object_id)
        if product_guard:
            await product_guard.check(db, actor, company, family)
        target = sku if sku else family
        permitted_family_states = (
            {"DRAFT", "ACTIVE"}
            if item
            or action in {"activate", "assign_categories", "create_variant", "configure_attributes"}
            else {"DRAFT"}
        )
        barcode_action = action in {"create_barcode", "barcode_state", "generate_barcode"}
        if family.status not in permitted_family_states or (
            sku is not None
            and sku.status != "DRAFT"
            and not (barcode_action and sku.status == "ACTIVE")
        ):
            raise ConflictError("structural product authoring requires draft products")
        if target.row_version != body.expected_version:
            raise ConflictError("product version changed; reload before editing")
        if target.row_version >= 2**31 - 1 or state.generation >= 2**63 - 1:
            raise ConflictError("product or company version exhausted")
        before = await access.values(target)
        target.row_version += 1
        target.updated_at, target.updated_by = utcnow(), actor.user_id
        work = ProductWork(db, actor, company, family, sku, access)
        await work.record(target, before, "update")
        # Protected reference reads refresh identity-map objects. Persist the checked
        # version inside this transaction before a nested configuration read can
        # refresh it; any handler failure still rolls the entire transaction back.
        await db.flush([target])
        category_dependencies = []
        if action in {"assign_categories", "activate"}:
            from catalog.models.product_definitions import FamilyCategory
            from catalog.schemas.product_authoring import CategoryAssignmentInput
            from catalog.tasks.category_membership import rows

            previous = await rows(access, FamilyCategory, FamilyCategory.family_id == family.id)
            if action == "activate":
                from catalog.schemas.activation import ActivationCommit

                assert isinstance(body, ActivationCommit)
                previous = [
                    row for row in previous if row.valid_to is None or row.valid_to >= body.as_of
                ]
            incoming = body.categories if isinstance(body, CategoryAssignmentInput) else []
            category_dependencies = [
                {
                    "scheme_id": str(entry.scheme_id),
                    "category_id": str(entry.category_id),
                    "is_primary": entry.is_primary,
                }
                for entry in [*previous, *incoming]
            ]
        await handler(work, body)
        state.generation += 1
        await db.flush()
        return CommandReceipt(
            200,
            {
                "category_dependencies": category_dependencies,
                "family_id": str(family.id),
                "item_id": str(work.item.id) if work.item else None,
                "ids": [str(value) for value in work.ids],
                "changed": {name: sorted(fields) for name, fields in work.changed.items()},
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> AuthoringResult:
        assert state is not None
        access = ConfigurationAccess(db, actor, company)
        family = await access.reference(ProductFamily, uuid.UUID(receipt["family_id"]))
        sku = (
            await access.reference(Item, uuid.UUID(receipt["item_id"]))
            if receipt["item_id"]
            else None
        )
        return AuthoringResult(
            family_id=family.id,
            family_version=family.row_version,
            item_id=sku.id if sku else None,
            item_version=sku.row_version if sku else None,
            changed_ids=receipt["ids"],
            policy_generation=state.generation,
        )

    try:
        if action == "activate":
            # Activation verifies every required price and freezes its source evidence.
            # Multiple levels need the same bounded budget as aggregate creation.
            return await execute_idempotent(
                factory,
                identity,
                authorize=authorize,
                mutate=mutate,
                render=render,
                timeout_seconds=30,
            )
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError("product definition conflicts or its references changed") from exc
