"""Protected native configuration storage, references and aggregate projection."""

import uuid
from collections.abc import Mapping
from typing import Any, TypeVar

from billing_platform.db.access import company_object
from billing_platform.db.base import Base
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ItemGroup
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.configuration import (
    CatalogDefaultProfile,
    ConfigurationRow,
    ProductConfigurationDraft,
    ProductConfigurationRevision,
    ProductConfigurationScope,
    ProductEntryOptionPolicy,
    ProductNumericDefault,
    ProductPricingPolicy,
)
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.products import Item, ProductFamily
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.models.returns import ReturnPolicyCondition, ReturnPolicyRevision
from catalog.schemas.configuration import (
    DraftDetail,
    DraftInput,
    EntryOptions,
    NumericInput,
    PricingRequirements,
    ProfileDefaults,
    RevisionDetail,
    ScopeDetail,
)
from catalog.tasks.field_context import FieldContext, FieldWriteChecks, load_field_context
from catalog.tasks.profile_bindings import BINDINGS

RowT = TypeVar("RowT", bound=Base)
CHILDREN = (
    ("options", ProductEntryOptionPolicy, EntryOptions),
    ("numeric_defaults", ProductNumericDefault, NumericInput),
    ("profiles", CatalogDefaultProfile, ProfileDefaults),
    ("pricing", ProductPricingPolicy, PricingRequirements),
)
SCOPE_OWNERS = {
    "TYPE": ("product_type_id", ProductType),
    "GROUP": ("group_id", ItemGroup),
    "FAMILY": ("family_id", ProductFamily),
    "SKU": ("item_id", Item),
}


class ConfigurationAccess:
    def __init__(self, db: AsyncSession, actor: Actor, company: uuid.UUID) -> None:
        self.db, self.actor, self.company = db, actor, company
        self.contexts: dict[str, FieldContext] = {}
        self.checks: dict[str, FieldWriteChecks] = {}
        self.subject_cache: dict[tuple[Any, ...], tuple[Any, ...]] = {}
        self.tax_rows: dict[tuple[Any, ...], list[Any]] = {}

    async def context(self, model: type[Any], permission: str | None = None) -> FieldContext:
        entity = "catalog." + model.__tablename__
        if entity not in self.contexts or permission is not None:
            self.contexts[entity] = await load_field_context(
                self.db,
                self.actor,
                self.company,
                entity,
                permission=permission,
                subject_cache=self.subject_cache,
            )
        return self.contexts[entity]

    async def values(self, row: Any) -> dict[str, Any]:
        context = await self.context(type(row))
        return {key: getattr(row, key) for key in context.native.fields}

    async def require(self, row: Any, keys: set[str] | None = None) -> None:
        context = await self.context(type(row))
        values = await self.values(row)
        if not (set(values) if keys is None else keys) <= context.readable(values):
            raise PermissionDeniedError("configuration requires readable dependency fields")

    async def scoped(self, model: type[RowT], object_id: uuid.UUID) -> RowT:
        await self.context(model)
        return await company_object(self.db, model, object_id, company_id=self.company)

    async def reference(self, model: type[Any], object_id: uuid.UUID) -> Any:
        context = await self.context(model)
        # Reject denied dependencies before an existence/activity lookup can become an oracle.
        if not set(context.native.fields) <= context.readable():
            raise PermissionDeniedError("configuration reference requires readable fields")
        row = await company_object(self.db, model, object_id, company_id=self.company)
        await self.require(row)
        if hasattr(row, "is_active") and not row.is_active:
            raise ConflictError("configuration references an inactive master")
        if hasattr(row, "published_at") and row.published_at is None:
            raise ConflictError("configuration requires a published revision")
        if isinstance(row, ProductTypeRevision):
            await self.reference(ProductType, row.product_type_id)
        if (
            isinstance(row, InventoryProfileTemplateRevision)
            and row.serial_tracking
            and row.identifier_profile_id is None
        ):
            raise ConflictError("Serial tracking requires a complete identifier profile")
        if (
            isinstance(row, InventoryProfileTemplateRevision)
            and row.identifier_profile_id is not None
        ):
            await self.reference(IdentifierProfile, row.identifier_profile_id)
        if isinstance(row, IdentifierProfile | ReturnPolicyRevision):
            child_model = (
                IdentifierProfileRequirement
                if isinstance(row, IdentifierProfile)
                else ReturnPolicyCondition
            )
            child_context = await self.context(child_model)
            if set(child_context.native.fields) - child_context.readable():
                raise PermissionDeniedError("profile requirement fields are protected")
        for binding in BINDINGS:
            if isinstance(row, binding.model):
                await self.reference(binding.parent, getattr(row, binding.parent_field))
        return row

    async def scope_owner(self, scope: ProductConfigurationScope) -> None:
        await self.require(
            scope,
            {"scope_kind", "owner_id", "row_version", "latest_revision"}
            if scope.scope_kind == "COMPANY"
            else None,
        )
        if scope.scope_kind != "COMPANY":
            field, model = SCOPE_OWNERS[scope.scope_kind]
            await self.reference(model, getattr(scope, field))

    async def company_scope(self, scope: ProductConfigurationScope) -> None:
        await self.require(scope, {"scope_kind", "owner_id"})
        if scope.scope_kind != "COMPANY" or scope.owner_id != self.company:
            raise ValidationFailedError(
                "only company-level product configuration can be changed; legacy scopes are history"
            )
        await self.scope_owner(scope)

    async def profile_references(self, profiles: ProfileDefaults) -> None:
        for key, kind in (
            ("goods_type_revision_id", "GOODS"),
            ("service_type_revision_id", "SERVICE"),
        ):
            value = getattr(profiles, key)
            if value is not None:
                revision = await self.reference(ProductTypeRevision, value)
                if revision.kind not in {kind, "BOTH"}:
                    raise ConflictError("configuration type default has an incompatible kind")
        for binding in BINDINGS:
            value = getattr(profiles, binding.field)
            if value is not None:
                await self.reference(binding.model, value)
        if profiles.identifier_profile_id is not None:
            await self.reference(IdentifierProfile, profiles.identifier_profile_id)

        if profiles.inventory_template_revision_id is not None:
            context = await self.context(InventoryProfileTemplateRevision)
            if "inventory" not in context.features:
                raise ConflictError("inventory profiles require enabled company inventory")
            inventory = await self.reference(
                InventoryProfileTemplateRevision, profiles.inventory_template_revision_id
            )
            for required, capability in (
                (inventory.lot_tracking, "batch_tracking"),
                (inventory.serial_tracking, "serial_tracking"),
                (inventory.expiry_required, "expiry_tracking"),
            ):
                if required and capability not in context.features:
                    raise ConflictError(f"inventory profiles require enabled company {capability}")

    async def write(self, row: Any, before: Mapping[str, Any]) -> frozenset[str]:
        context = await self.context(type(row))
        after = await self.values(row)
        changed = frozenset(
            key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
        )
        context.assert_writable(
            changed,
            before=before,
            after=after,
            checked=self.checks.setdefault(context.native.entity_type, FieldWriteChecks()),
        )
        return changed

    async def children(
        self,
        row: ProductConfigurationDraft | ProductConfigurationRevision,
        *,
        require: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        parent_field = "draft_id" if isinstance(row, ProductConfigurationDraft) else "revision_id"
        for key, model, schema in CHILDREN:
            context = await self.context(model)
            if parent_field not in context.readable():
                raise PermissionDeniedError("configuration child ownership is protected")
            rows = list(
                await self.db.scalars(
                    select(model)
                    .where(model.company_id == self.company, getattr(model, parent_field) == row.id)
                    .order_by(model.id)
                    .limit(8)
                )
            )
            if (key == "numeric_defaults" and len(rows) > 7) or (
                key != "numeric_defaults" and len(rows) != 1
            ):
                raise ConflictError("configuration has an incomplete or oversized native aggregate")
            values = []
            for child in rows:
                native = await self.values(child)
                if require:
                    await self.require(child)
                    values.append({field: getattr(child, field) for field in schema.model_fields})
                else:
                    values.append(
                        {
                            "id": child.id,
                            **{
                                field: value
                                for field, value in native.items()
                                if field in context.readable(native)
                            },
                        }
                    )
            result[key] = values if key == "numeric_defaults" else values[0]
        return result

    async def input(
        self, row: ProductConfigurationDraft | ProductConfigurationRevision
    ) -> DraftInput:
        await self.require(row)
        return DraftInput.model_validate(
            {
                "scope_id": row.scope_id,
                "effective_from": row.effective_from,
                "change_reason": row.change_reason,
                **await self.children(row, require=True),
            }
        )

    async def detail(self, row: ConfigurationRow, generation: int) -> BaseModel:
        context = await self.context(type(row))
        values = await self.values(row)
        result = {
            "id": row.id,
            "company_id": self.company,
            "created_at": row.created_at,
            "policy_generation": generation,
            **{key: value for key, value in values.items() if key in context.readable(values)},
        }
        if isinstance(row, ProductConfigurationScope):
            result["updated_at"] = row.updated_at
            return ScopeDetail.model_validate(result)
        assert isinstance(row, ProductConfigurationDraft | ProductConfigurationRevision)
        result.update(await self.children(row))
        if isinstance(row, ProductConfigurationDraft):
            result["updated_at"] = row.updated_at
            return DraftDetail.model_validate(result)
        return RevisionDetail.model_validate(result)
