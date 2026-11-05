"""Resolve the original actor from verified Identity facts before any Catalog access."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

from billing_platform.authz import Scope, ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import (
    CustomDefinition,
    condition_fields,
    condition_matches,
    decode_default,
)
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.field_metadata import (
    EffectiveField,
    FieldLayout,
    ScopedDefinition,
    resolve_custom_definitions,
    resolve_layout,
)
from billing_platform.field_policy import (
    FieldPolicyRule,
    assert_fields_writable,
    resolve_field_effect,
)
from billing_platform.fields import EntityFields
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.field_registry import CUSTOM_ENABLED_ENTITIES, registry
from catalog.domain.option_sources import OPTION_SOURCES
from catalog.models.projections import (
    CompanyFeatureProjection,
    CompanyProjection,
    CustomFieldDefinitionProjection,
    FieldConfigProjection,
    FieldPolicyProjection,
    RoleAssignmentProjection,
    RoleProjection,
    UserGroupMemberProjection,
    UserGroupProjection,
    UserProjection,
)
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from catalog.tasks.projections import require_identity_context

READ_PERMISSIONS = {
    "catalog.company_product_authoring_configuration": "product_configuration.read",
    "catalog.promotion_limit_definition": "promotion_limit.read",
    "catalog.promotion_limit_revision": "promotion_limit.read",

    "catalog.promotion_stack_draft": "promotion_stack_policy.read",
    "catalog.promotion_stack_draft_group": "promotion_stack_policy.read",
    "catalog.promotion_stack_draft_permission": "promotion_stack_policy.read",
    "catalog.promotion_stack_policy": "promotion_stack_policy.read",
    "catalog.promotion_stack_group": "promotion_stack_policy.read",
    "catalog.promotion_stack_permission": "promotion_stack_policy.read",
    **{
        f"catalog.{name}": "bom.read"
        for name in (
            "bom",
            "bom_draft",
            "bom_revision",
            "bom_component",
            "bom_output",
            "bom_assignment",
        )
    },
    "catalog.bulk_job": "catalog.bulk.read",
    "catalog.bulk_change_set": "catalog.bulk.read",
    "catalog.bulk_job_record": "catalog.bulk.read",
    "catalog.bulk_change_set_effect": "catalog.bulk.read",
    "catalog.bulk_job_dependency": "catalog.bulk.read",
    "catalog.bulk_import_artifact": "catalog.bulk.read",
    "catalog.tax_classification": "tax_rule.read",
    "catalog.tax_category": "tax_rule.read",
    "catalog.tax_rule_applicability": "tax_rule.read",
    "catalog.tax_release": "tax_rule.read",
    "catalog.tax_history_action": "tax_rule.read",
    "catalog.tax_rule": "tax_rule.read",
    "catalog.tax_rate_series": "tax_rule.read",
    "catalog.tax_rate": "tax_rule.read",
    "catalog.tax_rate_component": "tax_rule.read",
    "catalog.catalog_tax_scope": "tax_rule.read",
    "catalog.catalog_tax_binding": "tax_rule.read",
    "catalog.item_activation": "item.read",
    "catalog.item_activation_source": "item.read",
    "catalog.item_inventory_profile": "item.read",
    "catalog.item_stock_choice": "item.read",
    "catalog.item_regulatory_classification": "item.read",
    "catalog.price_level": "price_plan.read",
    "catalog.price_plan": "price_plan.read",
    "catalog.company_pricing_policy": "price_plan.read",
    "catalog.item_price_scope": "price_plan.read",
    "catalog.item_price_numeric_revision": "price_plan.read",
    "catalog.item_price_series": "price_plan.read",
    "catalog.item_price_draft": "price_plan.read",
    "catalog.item_price": "price_plan.read",
    "catalog.item_price_tier": "price_plan.read",
    "catalog.purchase_price_term": "purchase_price.read",
    "catalog.item_reference_cost": "reference_cost.read",
    "catalog.item_mrp": "price_plan.read",
    "catalog.item_price_formula": "price_plan.read",
    "catalog.commercial_policy_scope": "price_plan.read",
    "catalog.commercial_guard_rule": "price_plan.read",
    "catalog.discount_ceiling": "price_plan.read",
    "catalog.item_commercial_policy": "price_plan.read",
    "catalog.family_group_assignment": "item.read",
    "catalog.family_category": "item.read",
    "catalog.family_manufacturer": "item.read",
    "catalog.family_attribute": "item.read",
    "catalog.family_attribute_option": "item.read",
    "catalog.item_attribute_value": "item.read",
    "catalog.item_variant_key": "item.read",
    "catalog.item_unit_binding": "item.read",
    "catalog.item_unit_revision": "item.read",
    "catalog.item_barcode": "item.read",
    "catalog.product_configuration_adoption": "item.read",
    "catalog.product_configuration_adoption_source": "item.read",
    "catalog.product_configuration_scope": "product_configuration.read",
    "catalog.product_configuration_draft": "product_configuration.read",
    "catalog.product_configuration_revision": "product_configuration.read",
    "catalog.product_entry_option_policy": "product_configuration.read",
    "catalog.product_numeric_default": "product_configuration.read",
    "catalog.catalog_default_profile": "product_configuration.read",
    "catalog.product_pricing_policy": "product_configuration.read",
    "catalog.product_family": "item.read",
    "catalog.item": "item.read",
    "catalog.master_alias": "master_alias.read",
    "catalog.master_external_key": "master_external_key.read",
    "catalog.handling_profile": "handling_profile.read",
    "catalog.handling_profile_revision": "handling_profile.read",
    "catalog.sales_channel": "sales_channel.read",
    "catalog.return_policy": "return_policy.read",
    "catalog.return_policy_revision": "return_policy.read",
    "catalog.return_policy_condition": "return_policy.read",
    "catalog.manufacturing_route": "manufacturing_route.read",
    "catalog.manufacturing_route_revision": "manufacturing_route.read",
    "catalog.manufacturing_route_step": "manufacturing_route.read",
    "catalog.manufacturing_operation": "manufacturing_operation.read",
    "catalog.manufacturing_operation_revision": "manufacturing_operation.read",
    "catalog.warranty_policy": "warranty_policy.read",
    "catalog.warranty_policy_revision": "warranty_policy.read",
    "catalog.inventory_profile_template": "inventory_profile_template.read",
    "catalog.inventory_profile_template_revision": "inventory_profile_template.read",
    "catalog.item_group": "item_group.read",
    "catalog.item_group_parent": "item_group.read",
    "catalog.category_scheme": "category_scheme.read",
    "catalog.item_category": "item_category.read",
    "catalog.unit_of_measure": "unit.read",
    "catalog.unit_conversion": "unit.read",
    "catalog.unit_tax_code": "unit.read",
    "catalog.pack_type": "pack_type.read",
    "catalog.identifier_type": "identifier_type.read",
    "catalog.identifier_namespace": "identifier_namespace.read",
    "catalog.attribute_definition": "attribute_definition.read",
    "catalog.attribute_option": "attribute_option.read",
    "catalog.attribute_set": "attribute_set.read",
    "catalog.attribute_set_revision": "attribute_set.read",
    "catalog.attribute_set_member": "attribute_set.read",
    "catalog.identifier_profile": "identifier_profile.read",
    "catalog.identifier_profile_requirement": "identifier_profile.read",
    "catalog.brand": "brand.read",
    "catalog.manufacturer": "manufacturer.read",
    "catalog.brand_series": "brand_series.read",
    "catalog.manufacturer_site": "manufacturer_site.read",
    "catalog.brand_manufacturer": "brand_manufacturer.read",
    "catalog.product_type": "product_type.read",
    "catalog.product_type_revision": "product_type.read",
    "catalog.warehouse": "warehouse.read",
    "catalog.company_warehouse_configuration": "warehouse.read",
    "catalog.warehouse_operation_policy_revision": "warehouse.read",
    "catalog.warehouse_group": "warehouse_group.read",
    "catalog.warehouse_group_parent": "warehouse_group.read",
    # Reading a membership row is reading the group's composition, not the location's
    # detail. The members endpoint additionally requires `warehouse.read` and returns only
    # locations the actor's own scope reaches (docs/catalog-warehouses.md §3).
    "catalog.warehouse_group_assignment": "warehouse_group.read",
    "catalog.warehouse_bin": "warehouse_bin.read",
    # One read key across all three: they are the same per-product-per-location
    # definition, maintained by the same role. The policy read additionally requires
    # `warehouse.read` — it answers with location ids and composed operations, and a
    # reader who may not see locations must not enumerate them through a product.
    "catalog.item_warehouse_policy": "item_warehouse_policy.read",
    "catalog.item_warehouse_permission": "item_warehouse_policy.read",
    "catalog.item_replenishment_policy": "item_warehouse_policy.read",
    # A release and what a consumer acknowledged read under one key: the ack is only
    # meaningful next to the release it is about, and a reader who can see that a policy
    # was published should be able to see whether anything enforces it (§5).
    "catalog.catalog_policy_release": "catalog.release.read",
    "catalog.catalog_policy_consumer_ack": "catalog.release.read",
}
MANAGE_PERMISSIONS = {
    "catalog.company_product_authoring_configuration": "product_configuration.manage",
    "catalog.promotion_limit_definition": "promotion_limit.manage",
    "catalog.promotion_limit_revision": "promotion_limit.manage",

    "catalog.promotion_stack_draft": "promotion_stack_policy.manage",
    "catalog.promotion_stack_draft_group": "promotion_stack_policy.manage",
    "catalog.promotion_stack_draft_permission": "promotion_stack_policy.manage",
    "catalog.promotion_stack_policy": "promotion_stack_policy.manage",
    "catalog.promotion_stack_group": "promotion_stack_policy.manage",
    "catalog.promotion_stack_permission": "promotion_stack_policy.manage",
    **{
        f"catalog.{name}": "bom.manage"
        for name in ("bom", "bom_draft", "bom_revision", "bom_component", "bom_output")
    },
    "catalog.bom_assignment": "bom.assign",
    "catalog.bulk_job": "catalog.bulk.manage",
    "catalog.bulk_change_set": "catalog.bulk.manage",
    "catalog.bulk_job_record": "catalog.bulk.manage",
    "catalog.bulk_change_set_effect": "catalog.bulk.manage",
    "catalog.bulk_job_dependency": "catalog.bulk.manage",
    "catalog.bulk_import_artifact": "catalog.bulk.manage",
    "catalog.tax_classification": "tax_rule.manage",
    "catalog.tax_category": "tax_rule.manage",
    "catalog.tax_rule_applicability": "tax_rule.manage",
    "catalog.tax_release": "tax_rule.manage",
    "catalog.tax_history_action": "tax_rule.manage",
    "catalog.tax_rule": "tax_rule.manage",
    "catalog.tax_rate_series": "tax_rule.manage",
    "catalog.tax_rate": "tax_rule.manage",
    "catalog.tax_rate_component": "tax_rule.manage",
    "catalog.catalog_tax_scope": "tax_rule.manage",
    "catalog.catalog_tax_binding": "tax_rule.manage",
    "catalog.item_activation": "item.activate",
    "catalog.item_activation_source": "item.activate",
    "catalog.item_inventory_profile": "item.activate",
    "catalog.item_stock_choice": "item.update",
    "catalog.item_regulatory_classification": "item.activate",
    "catalog.price_level": "price_plan.manage",
    "catalog.price_plan": "price_plan.manage",
    "catalog.company_pricing_policy": "price_plan.manage",
    "catalog.item_price_scope": "price_plan.manage",
    "catalog.item_price_numeric_revision": "price_plan.manage",
    "catalog.item_price_series": "price_plan.manage",
    "catalog.item_price_draft": "price_plan.manage",
    "catalog.item_price": "price_plan.manage",
    "catalog.item_price_tier": "price_plan.manage",
    "catalog.purchase_price_term": "purchase_price.manage",
    "catalog.item_reference_cost": "reference_cost.manage",
    "catalog.item_mrp": "price_plan.manage",
    "catalog.item_price_formula": "price_plan.manage",
    "catalog.commercial_policy_scope": "price_plan.manage",
    "catalog.commercial_guard_rule": "price_plan.manage",
    "catalog.discount_ceiling": "price_plan.manage",
    "catalog.item_commercial_policy": "price_plan.manage",
    "catalog.family_group_assignment": "item.update",
    "catalog.family_category": "item.update",
    "catalog.family_manufacturer": "item.update",
    "catalog.family_attribute": "item.update",
    "catalog.family_attribute_option": "item.update",
    "catalog.item_attribute_value": "item.update",
    "catalog.item_variant_key": "item.update",
    "catalog.item_unit_binding": "item.update",
    "catalog.item_unit_revision": "item.update",
    "catalog.item_barcode": "item.update",
    "catalog.product_configuration_adoption": "item.update",
    "catalog.product_configuration_adoption_source": "item.update",
    "catalog.product_configuration_scope": "product_configuration.manage",
    "catalog.product_configuration_draft": "product_configuration.manage",
    "catalog.product_configuration_revision": "product_configuration.manage",
    "catalog.product_entry_option_policy": "product_configuration.manage",
    "catalog.product_numeric_default": "product_configuration.manage",
    "catalog.catalog_default_profile": "product_configuration.manage",
    "catalog.product_pricing_policy": "product_configuration.manage",
    "catalog.product_family": "item.update",
    "catalog.item": "item.update",
    "catalog.master_alias": "master_alias.manage",
    "catalog.master_external_key": "master_external_key.manage",
    "catalog.handling_profile": "handling_profile.manage",
    "catalog.handling_profile_revision": "handling_profile.manage",
    "catalog.sales_channel": "sales_channel.manage",
    "catalog.return_policy": "return_policy.manage",
    "catalog.return_policy_revision": "return_policy.manage",
    "catalog.return_policy_condition": "return_policy.manage",
    "catalog.manufacturing_route": "manufacturing_route.manage",
    "catalog.manufacturing_route_revision": "manufacturing_route.manage",
    "catalog.manufacturing_route_step": "manufacturing_route.manage",
    "catalog.manufacturing_operation": "manufacturing_operation.manage",
    "catalog.manufacturing_operation_revision": "manufacturing_operation.manage",
    "catalog.warranty_policy": "warranty_policy.manage",
    "catalog.warranty_policy_revision": "warranty_policy.manage",
    "catalog.inventory_profile_template": "inventory_profile_template.manage",
    "catalog.inventory_profile_template_revision": "inventory_profile_template.manage",
    "catalog.item_group": "item_group.manage",
    "catalog.item_group_parent": "item_group.move",
    "catalog.category_scheme": "category_scheme.manage",
    "catalog.item_category": "item_category.manage",
    "catalog.unit_of_measure": "unit.manage",
    "catalog.unit_conversion": "unit.manage",
    "catalog.unit_tax_code": "unit.manage",
    "catalog.pack_type": "pack_type.manage",
    "catalog.identifier_type": "identifier_type.manage",
    "catalog.identifier_namespace": "identifier_namespace.manage",
    "catalog.attribute_definition": "attribute_definition.manage",
    "catalog.attribute_option": "attribute_option.manage",
    "catalog.attribute_set": "attribute_set.manage",
    "catalog.attribute_set_revision": "attribute_set.manage",
    "catalog.attribute_set_member": "attribute_set.manage",
    "catalog.identifier_profile": "identifier_profile.manage",
    "catalog.identifier_profile_requirement": "identifier_profile.manage",
    "catalog.brand": "brand.manage",
    "catalog.manufacturer": "manufacturer.manage",
    "catalog.brand_series": "brand_series.manage",
    "catalog.manufacturer_site": "manufacturer_site.manage",
    "catalog.brand_manufacturer": "brand_manufacturer.manage",
    "catalog.product_type": "product_type.manage",
    "catalog.product_type_revision": "product_type.manage",
    "catalog.warehouse": "warehouse.manage",
    "catalog.company_warehouse_configuration": "warehouse.manage",
    # Writing the row needs `manage`; *publishing* one adds `warehouse.publish` at the
    # command boundary. Keeping them separate is what lets a location inherit Main's
    # reviewed policy on create without the creator holding publish rights.
    "catalog.warehouse_operation_policy_revision": "warehouse.manage",
    "catalog.warehouse_group": "warehouse_group.manage",
    "catalog.warehouse_group_parent": "warehouse_group.move",
    # Assigning a location to a group is a grouping change, not a change to the location:
    # it grants nothing, so it stays with the grouping permission.
    "catalog.warehouse_group_assignment": "warehouse_group.manage",
    "catalog.warehouse_bin": "warehouse_bin.manage",
    # One manage key across all three, and no publish key: none of them moves money or
    # posts, and the location's own reviewed policy is still the ceiling, so splitting
    # them would add keys with no separation-of-duties reason behind them.
    "catalog.item_warehouse_policy": "item_warehouse_policy.manage",
    "catalog.item_warehouse_permission": "item_warehouse_policy.manage",
    "catalog.item_replenishment_policy": "item_warehouse_policy.manage",
    # Publishing a release adds `warehouse.publish` at the command boundary, as an
    # operation-policy revision does: a release delivers reviewed location policy, so the
    # authority to write one is the authority to publish that policy.
    "catalog.catalog_policy_release": "warehouse.manage",
    # An acknowledgement is a trusted consumer's statement, ingested from a signed event and
    # never written by an actor. The key is here because the shared write path demands one
    # for the entity it is recording; no HTTP route reaches this table
    # (docs/catalog-warehouse-plan.md, Phase 6).
    "catalog.catalog_policy_consumer_ack": "warehouse.manage",
}
NUMERIC_FIELDS = frozenset(
    {
        "basis_quantity",
        "change_count",
        "entity_version",
        "source_version",
        "policy_generation",
        "latest_revision",
        "quantity_decimal_places",
        "price_decimal_places",
        "price_increment",
        "price_basis_quantity",
        "sale_level_count",
        "nominal_ratio",
        "primary_slot",
        "min_sale_quantity",
        "default_slot",
        "amount",
        "min_quantity",
        "max_quantity",
        "gross_amount",
        "discount_value",
        "percentage",
        "max_discount_pct",
        "ordinal",
        "decimal_places",
        "quantity_increment",
        "row_version",
        "revision",
        "numerator",
        "denominator",
        "value_integer",
        "value_decimal",
        "position",
        "normalization_version",
        "min_count",
        "max_count",
        "duration",
        "temperature_min",
        "temperature_max",
        "window_days",
        "condition_count",
        "shelf_life_days",
        "minimum_remaining_life_days",
        "safety_quantity",
        "reorder_quantity",
        "target_quantity",
        "min_order_quantity",
        "max_order_quantity",
        "order_multiple",
        "lead_time_days",
    }
)


def numeric_keys(definitions: tuple[CustomDefinition, ...]) -> frozenset[str]:
    return NUMERIC_FIELDS | frozenset(
        "custom_field:" + definition.key
        for definition in definitions
        if definition.data_type in {"integer", "decimal"}
    )


def condition_scalar(key: str, value: Any, numeric: frozenset[str]) -> Any:
    if value is None:
        return None
    if key in numeric:
        if key in {"numerator", "denominator", "value_integer"}:
            if (
                isinstance(value, bool)
                or not isinstance(value, int | str | Decimal)
                or len(str(value)) > 128
            ):
                raise ValueError("invalid integer predicate")
            try:
                result = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("invalid integer predicate") from exc
            if (
                not result.is_finite()
                or result != result.to_integral_value()
                or result < (-(2**63) if key == "value_integer" else -(2**63 - 1))
                or result > 2**63 - 1
            ):
                raise ValueError("integer predicate exceeds its native range")
            return result
        return exact_decimal(value)
    if not key.startswith("custom_field:") and key.endswith("_id"):
        return str(uuid.UUID(str(value)))
    if key in {"valid_from", "valid_to"}:
        return dt.date.fromisoformat(str(value)).isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


def condition_tree(tree: dict[str, Any], numeric: frozenset[str]) -> dict[str, Any]:
    if "op" in tree:
        return {**tree, "rules": [condition_tree(rule, numeric) for rule in tree["rules"]]}
    if tree["cmp"] in {"empty", "not_empty"}:
        return tree
    if tree["field"] in numeric and tree["cmp"] == "matches":
        raise ValueError("numeric predicates do not use text patterns")
    value = tree["value"]
    if tree["cmp"] in {"in", "not_in"}:
        value = [condition_scalar(tree["field"], member, numeric) for member in value]
    else:
        value = condition_scalar(tree["field"], value, numeric)
    return {**tree, "value": value}


@dataclass(frozen=True)
class FieldPresentation:
    help_text: str | None = None
    placeholder: str | None = None
    display_group: str | None = None
    suggested_value: str | None = None
    label: str | None = None


@dataclass
class FieldWriteChecks:
    """Transaction-local native values for a second current-policy check.

    These values never enter a persisted receipt. Mutable child receipts from
    earlier transactions must still use conservative authorization.
    """

    writes: list[tuple[frozenset[str], dict[str, Any], dict[str, Any]]] = field(
        default_factory=list
    )

    def recheck(self, context: FieldContext) -> None:
        for changed, before, after in self.writes:
            context.assert_writable(changed, before=before, after=after)


@dataclass(frozen=True)
class FieldContext:
    company: CompanyProjection
    native: EntityFields
    source_version: int
    features: frozenset[str]
    definitions: tuple[CustomDefinition, ...]
    fields: tuple[EffectiveField, ...]
    policies: tuple[FieldPolicyProjection, ...]
    presentation: Mapping[str, FieldPresentation] = field(default_factory=dict)

    def rules(self, values: Mapping[str, Any] | None = None) -> tuple[FieldPolicyRule, ...]:
        rules = []
        numeric = numeric_keys(self.definitions)
        normalized = (
            None
            if values is None
            else {key: condition_scalar(key, value, numeric) for key, value in values.items()}
        )
        for policy in self.policies:
            if policy.predicate_json is not None:
                if values is None:
                    if policy.effect != "deny":
                        continue
                elif not condition_matches(
                    condition_tree(policy.predicate_json, numeric), normalized or {}
                ):
                    continue
            rules.append(
                FieldPolicyRule(
                    policy.field_key,
                    policy.access,
                    policy.effect,
                    Scope(policy.scope_type, policy.scope_id),
                )
            )
        return tuple(rules)

    def readable(self, values: Mapping[str, Any] | None = None) -> frozenset[str]:
        fields = set(self.native.fields) | {
            "custom_field:" + definition.key for definition in self.definitions
        }
        rules = self.rules(values)
        return frozenset(
            key
            for key in fields
            if resolve_field_effect(
                rules,
                field_key=key,
                access="read",
                target=ScopePath(company_id=self.company.company_id),
            )
            == "allow"
        )

    def assert_writable(
        self,
        changed: frozenset[str],
        *,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        checked: FieldWriteChecks | None = None,
    ) -> None:
        for values in (before, after):
            assert_fields_writable(
                changed,
                rules=self.rules(values),
                target=ScopePath(company_id=self.company.company_id),
            )
        if checked is not None:
            checked.writes.append((changed, dict(before), dict(after)))


def custom_default(kind: str, value: str | None) -> Any:
    return decode_default(kind, value)


def custom_definition(
    row: CustomFieldDefinitionProjection, features: frozenset[str] = frozenset()
) -> CustomDefinition:
    if set(row.options or {}) - {"choices"}:
        raise ValueError("unsupported custom option configuration")
    return CustomDefinition.model_validate(
        {
            "key": row.definition_key,
            "data_type": row.data_type,
            "is_active": row.is_active
            and (row.requires_feature is None or row.requires_feature in features),
            "is_searchable": row.is_searchable,
            "is_immutable_after_create": row.is_immutable_after_create,
            "validation": row.validation or {},
            "choices": (row.options or {}).get("choices", []),
            "option_source_key": row.option_source_key,
            "depends_on_key": row.depends_on_key,
            "visibility": row.visibility,
            "default_value": custom_default(row.data_type, row.default_value),
            "sequence_config": row.sequence_config,
        }
    )


async def load_field_context(
    db: AsyncSession,
    actor: Actor,
    company_id: uuid.UUID,
    entity_type: str,
    *,
    permission: str | None = None,
    subject_cache: dict[tuple[Any, ...], tuple[Any, ...]] | None = None,
    candidates: bool = False,
) -> FieldContext:
    native = registry.get(entity_type)
    required = permission or READ_PERMISSIONS[entity_type]
    actor.require_scope(required, target=ScopePath(company_id=company_id))
    if actor.tenant_id != require_current_tenant():
        raise PermissionDeniedError("actor differs from the transaction tenant")
    checkpoint = await require_identity_context(db, company_id)
    cache_key = (
        actor.tenant_id,
        company_id,
        actor.user_id,
        checkpoint.source_version,
        utcnow().date(),
    )
    cached_subject = None if subject_cache is None else subject_cache.get(cache_key)
    if cached_subject is not None:
        company, groups, active_roles = cached_subject
    else:
        company = await db.scalar(
            select(CompanyProjection).where(
                CompanyProjection.company_id == company_id,
                CompanyProjection.source_id == company_id,
            )
        )
        if company is None:
            raise IdentitySourceUnavailableError("company source is unavailable")
        if company.status != "active":
            raise PermissionDeniedError("company is not active")
        user = await db.scalar(
            select(UserProjection).where(
                UserProjection.company_id == company_id, UserProjection.source_id == actor.user_id
            )
        )
        if user is None or user.status != "active":
            raise PermissionDeniedError("actor is not an active company source subject")
        memberships = list(
            await db.scalars(
                select(UserGroupMemberProjection.user_group_id)
                .where(
                    UserGroupMemberProjection.company_id == company_id,
                    UserGroupMemberProjection.user_id == actor.user_id,
                )
                .limit(1001)
            )
        )
        if len(memberships) > 1000:
            raise IdentitySourceUnavailableError("subject membership exceeds bounded resolution")
        groups = list(
            await db.scalars(
                select(UserGroupProjection.source_id).where(
                    UserGroupProjection.company_id == company_id,
                    UserGroupProjection.source_id.in_(memberships),
                    UserGroupProjection.is_active.is_(True),
                )
            )
        )
        today = utcnow().date()
        roles = list(
            await db.scalars(
                select(RoleAssignmentProjection.role_id)
                .where(
                    RoleAssignmentProjection.company_id == company_id,
                    RoleAssignmentProjection.is_active.is_(True),
                    RoleAssignmentProjection.valid_from <= today,
                    or_(
                        RoleAssignmentProjection.valid_to.is_(None),
                        RoleAssignmentProjection.valid_to >= today,
                    ),
                    or_(
                        (RoleAssignmentProjection.subject_type == "user")
                        & (RoleAssignmentProjection.subject_id == actor.user_id),
                        (RoleAssignmentProjection.subject_type == "user_group")
                        & RoleAssignmentProjection.subject_id.in_(groups),
                    ),
                )
                .limit(1001)
            )
        )
        if len(roles) > 1000:
            raise IdentitySourceUnavailableError("role assignment exceeds bounded resolution")
        active_roles = list(
            await db.scalars(
                select(RoleProjection.source_id).where(
                    RoleProjection.company_id == company_id,
                    RoleProjection.source_id.in_(roles),
                    RoleProjection.is_active.is_(True),
                )
            )
        )
        if subject_cache is not None:
            subject_cache[cache_key] = (company, groups, active_roles)
    policies = tuple(
        await db.scalars(
            select(FieldPolicyProjection)
            .where(
                FieldPolicyProjection.company_id == company_id,
                FieldPolicyProjection.entity_type == entity_type,
                FieldPolicyProjection.is_active.is_(True),
                or_(
                    (FieldPolicyProjection.subject_type == "user")
                    & (FieldPolicyProjection.subject_id == actor.user_id),
                    (FieldPolicyProjection.subject_type == "user_group")
                    & FieldPolicyProjection.subject_id.in_(groups),
                    (FieldPolicyProjection.subject_type == "role")
                    & FieldPolicyProjection.subject_id.in_(active_roles),
                ),
            )
            .limit(1001)
        )
    )
    if len(policies) > 1000:
        raise IdentitySourceUnavailableError("field policies exceed bounded resolution")
    features = frozenset(
        await db.scalars(
            select(CompanyFeatureProjection.feature_key)
            .where(
                CompanyFeatureProjection.company_id == company_id,
                CompanyFeatureProjection.is_enabled.is_(True),
            )
            .limit(1001)
        )
    )
    definitions = tuple(
        await db.scalars(
            select(CustomFieldDefinitionProjection)
            .where(
                CustomFieldDefinitionProjection.company_id == company_id,
                CustomFieldDefinitionProjection.entity_type == entity_type,
            )
            .limit(257)
        )
    )
    layouts = tuple(
        await db.scalars(
            select(FieldConfigProjection)
            .where(
                FieldConfigProjection.company_id == company_id,
                FieldConfigProjection.entity_type == entity_type,
            )
            .limit(513)
        )
    )
    if len(definitions) > 256 or len(layouts) > 512 or len(features) > 1000:
        raise IdentitySourceUnavailableError("field source exceeds bounded resolution")
    try:
        if definitions and entity_type not in CUSTOM_ENABLED_ENTITIES:
            raise ValueError("custom fields are unsupported on this entity")
        resolved = resolve_custom_definitions(
            (
                ScopedDefinition(
                    actor.tenant_id,
                    None if row.source_company_id == SCOPE_ALL else row.source_company_id,
                    custom_definition(row, features),
                    row.source_version,
                )
                for row in definitions
            ),
            tenant_id=actor.tenant_id,
            company_id=company_id,
            native_fields=frozenset(native.fields),
            option_sources=frozenset(OPTION_SOURCES),
        )
        for definition in resolved:
            if definition.option_source_key is not None:
                source = OPTION_SOURCES[definition.option_source_key]
                if (source.parent_source is None) != (definition.depends_on_key is None):
                    raise ValueError("option source requires its declared parent contract")
                if source.parent_source is not None:
                    parent_definition = next(
                        (item for item in resolved if item.key == definition.depends_on_key), None
                    )
                    if (
                        parent_definition is None
                        or parent_definition.option_source_key != source.parent_source
                    ):
                        raise ValueError(
                            "category options require a category-scheme reference parent"
                        )
        selected = {
            row.definition_key: row
            for row in sorted(definitions, key=lambda row: row.source_company_id != SCOPE_ALL)
        }
        if not candidates and entity_type in {"catalog.item", "catalog.product_family"}:
            from catalog.tasks.field_adoption import accepted_definitions

            resolved = await accepted_definitions(
                db, company_id, entity_type, resolved, selected, features
            )
        known = frozenset(native.fields) | {
            "custom_field:" + definition.key for definition in resolved
        }
        for policy in policies:
            if policy.field_key not in known:
                raise ValueError("policy refers to an unknown field")
            if policy.predicate_json is not None:
                condition_fields(policy.predicate_json, allowed=known)
                condition_tree(policy.predicate_json, numeric_keys(resolved))
        effective = resolve_layout(
            native,
            resolved,
            (
                FieldLayout(
                    actor.tenant_id,
                    None if row.source_company_id == SCOPE_ALL else row.source_company_id,
                    cast(Literal["native", "custom"], row.field_source),
                    row.field_key,
                    visible=row.is_visible,
                    required=row.is_required,
                    label=row.label_override,
                    order=row.display_order,
                )
                for row in layouts
            ),
            tenant_id=actor.tenant_id,
            company_id=company_id,
            enabled_features=features,
        )
    except (ValueError, PermissionDeniedError, ValidationFailedError) as exc:
        raise IdentitySourceUnavailableError("field source cannot be safely resolved") from exc
    # Layout requiredness is part of write validation; keep disabled definitions
    # present so a disabled company override cannot resurrect its tenant default.
    by_key = {field.key: field.definition for field in effective if field.definition is not None}
    resolved = tuple(by_key.get(definition.key, definition) for definition in resolved)
    selected = {
        row.definition_key: row
        for row in sorted(definitions, key=lambda row: row.source_company_id != SCOPE_ALL)
    }
    configured_labels = {row.field_key for row in layouts if row.label_override is not None}
    configured_order = {row.field_key for row in layouts if row.display_order is not None}
    effective = tuple(
        replace(
            field,
            label=selected[field.key].label if field.key not in configured_labels else field.label,
            order=selected[field.key].display_order
            if field.key not in configured_order
            else field.order,
        )
        if field.source == "custom"
        else field
        for field in effective
    )
    effective = tuple(sorted(effective, key=lambda field: (field.order, field.source, field.key)))
    presentation = {
        "custom_field:" + key: FieldPresentation(
            row.help_text, row.placeholder, row.display_group, label=row.label
        )
        for key, row in selected.items()
    }
    default_overrides: dict[str, Any] = {}
    for layout in sorted(layouts, key=lambda row: row.source_company_id != SCOPE_ALL):
        key = (
            layout.field_key
            if layout.field_source == "native"
            else "custom_field:" + layout.field_key
        )
        current = presentation.get(key, FieldPresentation())
        presentation[key] = replace(
            current,
            label=layout.label_override if layout.label_override is not None else current.label,
            help_text=layout.help_text_override
            if layout.help_text_override is not None
            else current.help_text,
            display_group=layout.display_group
            if layout.display_group is not None
            else current.display_group,
            suggested_value=layout.default_value
            if layout.default_value is not None
            else current.suggested_value,
        )
        if layout.field_source == "custom" and layout.default_value is not None:
            default_overrides[layout.field_key] = layout.default_value
    try:
        resolved = tuple(
            CustomDefinition.model_validate(
                {
                    **definition.model_dump(),
                    "default_value": custom_default(
                        definition.data_type, default_overrides[definition.key]
                    ),
                }
            )
            if definition.key in default_overrides
            and (candidates or not selected[definition.key].requires_adoption)
            else definition
            for definition in resolved
        )
    except ValueError as exc:
        raise IdentitySourceUnavailableError("field default cannot be safely resolved") from exc
    by_key = {definition.key: definition for definition in resolved}
    effective = tuple(
        replace(
            item,
            definition=by_key[item.key],
            required=by_key[item.key].validation.required,
            visible=item.visible and by_key[item.key].is_active,
        )
        if item.definition is not None
        else item
        for item in effective
    )
    return FieldContext(
        company,
        native,
        checkpoint.source_version,
        features,
        resolved,
        effective,
        policies,
        presentation,
    )
