"""Authenticated, source-gated native/custom form metadata."""

import uuid
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.custom_fields import condition_fields
from billing_platform.db.access import company_object
from billing_platform.errors import ErrorEnvelope, PermissionDeniedError, ValidationFailedError
from billing_platform.field_metadata import EffectiveField
from billing_platform.field_policy import resolve_field_effect
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.models.products import Item, ProductFamily
from catalog.schemas.field_metadata import FieldMetadata, FieldSet
from catalog.tasks.bom_controls import ENTITIES as BOM_ENTITIES
from catalog.tasks.bom_controls import PUBLISH_PERMISSIONS as BOM_PUBLISH_PERMISSIONS
from catalog.tasks.company_product_controls import company_control
from catalog.tasks.configuration_controls import ENTRY_HELP, PRICING_HELP, UNIT_OPTIONS
from catalog.tasks.configuration_controls import control as configuration_control
from catalog.tasks.definition_controls import (
    ENTITIES as DEFINITION_ENTITIES,
)
from catalog.tasks.definition_controls import (
    GENERATED as DEFINITION_GENERATED,
)
from catalog.tasks.definition_controls import (
    PUBLISH_PERMISSIONS as DEFINITION_PUBLISH_PERMISSIONS,
)
from catalog.tasks.definition_controls import (
    REVISIONS as DEFINITION_REVISIONS,
)
from catalog.tasks.field_context import MANAGE_PERMISSIONS, FieldPresentation, load_field_context
from catalog.tasks.product_profile_controls import MASTERS as PROFILE_MASTERS
from catalog.tasks.product_profile_controls import PUBLISH_PERMISSIONS
from catalog.tasks.promotion_stack_controls import (
    ENTITIES as STACK_ENTITIES,
)
from catalog.tasks.promotion_stack_controls import (
    PUBLISH_PERMISSIONS as STACK_PUBLISH_PERMISSIONS,
)
from catalog.tasks.promotion_stack_controls import (
    PUBLISHED as STACK_PUBLISHED,
)

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 503)},
)


@router.get(
    "/entities/{entity_type}/field-set",
    response_model=FieldSet,
    operation_id="get_catalog_field_set",
)
async def field_set(
    company_id: uuid.UUID,
    entity_type: str,
    request: Request,
    operation: Literal["create", "update", "publish"] | None = None,
    object_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> FieldSet:
    if set(request.query_params) - {"operation", "object_id"} or len(
        request.query_params.multi_items()
    ) != len(request.query_params):
        raise ValidationFailedError("unsupported or duplicate field-set query parameter")
    if object_id is not None and (
        operation != "update" or entity_type not in {"catalog.item", "catalog.product_family"}
    ):
        raise ValidationFailedError("object metadata requires a product update operation")
    context = await load_field_context(db, current, company_id, entity_type)
    publication_permissions = {
        **BOM_PUBLISH_PERMISSIONS,
        **DEFINITION_PUBLISH_PERMISSIONS,
        **STACK_PUBLISH_PERMISSIONS,
        **PUBLISH_PERMISSIONS,
        "catalog.attribute_set_revision": "attribute_set.publish",
        "catalog.attribute_set_member": "attribute_set.publish",
        "catalog.product_type_revision": "product_type.publish",
        "catalog.catalog_policy_release": "warehouse.publish",
    }
    if operation == "publish" and entity_type not in publication_permissions:
        raise ValidationFailedError("publication metadata is unsupported for this entity")
    product = entity_type in {"catalog.item", "catalog.product_family"}
    writable_resource = current.allows_scope(
        publication_permissions[entity_type]
        if operation == "publish"
        else "item.create"
        if product and operation == "create"
        else "warehouse_group.manage"
        if entity_type == "catalog.warehouse_group_parent" and operation == "create"
        else MANAGE_PERMISSIONS[entity_type],
        target=ScopePath(company_id=company_id),
    )
    if entity_type == "catalog.warehouse" and operation == "create":
        writable_resource &= {"inventory", "multi_godown"} <= set(context.features)
    if product and operation is None:
        writable_resource |= current.allows_scope(
            "item.create", target=ScopePath(company_id=company_id)
        )
    existing = None
    if object_id is not None:
        existing = await company_object(
            db,
            Item if entity_type == "catalog.item" else ProductFamily,
            object_id,
            company_id=company_id,
        )
    assert existing is None or isinstance(existing, Item | ProductFamily)
    native_values = (
        None
        if existing is None
        else {name: getattr(existing, name) for name in context.native.fields}
    )
    if native_values is not None:
        assert existing is not None
        native_values.update(
            {"custom_field:" + k: v for k, v in (existing.custom_fields or {}).items()}
        )
    readable = context.readable(native_values)
    rules = context.rules(native_values)
    conditional = {row.field_key for row in context.policies if row.predicate_json is not None}
    readonly = {"row_version"}
    if entity_type == "catalog.catalog_policy_release":
        readonly |= set(context.native.fields) - {"effective_date", "change_reason"}
    if entity_type in DEFINITION_ENTITIES:
        if "sales_promotions" not in context.features:
            writable_resource = False
        if entity_type in DEFINITION_REVISIONS:
            readonly |= set(DEFINITION_GENERATED) | {DEFINITION_REVISIONS[entity_type]}
            if operation == "publish":
                readonly -= set(context.native.fields)
        elif operation == "update":
            readonly.add("is_active")

    if entity_type in STACK_ENTITIES:
        if "sales_promotions" not in context.features:
            writable_resource = False
        if entity_type in STACK_PUBLISHED and operation != "publish":
            readonly |= set(context.native.fields)
        elif entity_type == "catalog.promotion_stack_draft":
            readonly |= {"status", "group_count", "permission_count", "published_policy_id"}
            if operation == "publish":
                readonly -= {"status", "published_policy_id", "row_version"}

    if entity_type in BOM_ENTITIES:
        if not {"inventory", "bom_definitions"} <= context.features:
            writable_resource = False
        if entity_type == "catalog.bom" and operation == "update":
            readonly.add("is_active")
        if entity_type in {"catalog.bom_draft", "catalog.bom_revision"}:
            readonly |= {
                "draft_number",
                "revision",
                "status",
                "published_revision_id",
                "published_at",
                "component_count",
                "output_count",
                "content_sha256",
                "dependency_manifest",
                "policy_generation",
                "source_version",
                "bom_id",
                "draft_id",
            }
            if operation == "create" and entity_type == "catalog.bom_draft":
                readonly.discard("bom_id")
            if operation == "publish":
                readonly -= {"status", "published_revision_id", "published_at"}
                if entity_type == "catalog.bom_revision":
                    # Publication creates these values from the reviewed draft; expose
                    # their field authority without accepting them in the command DTO.
                    readonly -= set(context.native.fields)
    if operation == "update" and entity_type in PROFILE_MASTERS:
        readonly.add("is_active")
    if operation == "update" and entity_type == "catalog.sales_channel":
        readonly.add("is_active")  # Dedicated lifecycle commands.
    if operation == "update" and entity_type in {"catalog.price_level", "catalog.price_plan"}:
        editable = {"name", "is_active"} if entity_type == "catalog.price_level" else {"name"}
        readonly |= set(context.native.fields) - editable
    if operation == "update" and entity_type in {
        "catalog.attribute_definition",
        "catalog.attribute_option",
        "catalog.attribute_set",
    }:
        readonly.add("is_active")
        if entity_type == "catalog.attribute_option":
            readonly |= {"definition_id", "value_type"}
    if operation == "update" and entity_type in {
        "catalog.unit_conversion",
        "catalog.identifier_profile_requirement",
    }:
        readonly |= set(context.native.fields)
    if operation == "update" and entity_type in {
        "catalog.pack_type",
        "catalog.identifier_type",
        "catalog.identifier_namespace",
        "catalog.identifier_profile",
    }:
        readonly.add("is_active")
        if entity_type in {"catalog.identifier_type", "catalog.identifier_namespace"}:
            readonly |= {"code", "is_barcode"}
        if entity_type == "catalog.identifier_profile":
            readonly.add("code")
    if operation == "update" and entity_type in {
        "catalog.warehouse_bin",
        "catalog.warehouse_group",
    }:
        readonly.add("is_active")  # Lifecycle has dedicated audited commands.
        if entity_type == "catalog.warehouse_bin":
            readonly.add("warehouse_id")
    if operation == "update" and entity_type in {
        "catalog.tax_category",
        "catalog.tax_rule",
        "catalog.tax_classification",
        "catalog.tax_rate_series",
        "catalog.tax_rate",
        "catalog.tax_rate_component",
    }:
        # Only category/rule descriptive fields can be patched. Dated definitions
        # and component children are replaced through publication commands.
        editable = (
            {"name", "is_active", "custom_fields"}
            if entity_type in {"catalog.tax_category", "catalog.tax_rule"}
            else set()
        )
        readonly |= set(context.native.fields) - editable
    if entity_type in {
        "catalog.item_activation",
        "catalog.item_activation_source",
        "catalog.item_inventory_profile",
    }:
        readonly |= set(context.native.fields)
    if entity_type == "catalog.catalog_tax_scope":
        readonly.add("owner_id")
    pricing_generated = {
        "catalog.item_price_draft": {"status", "item_id", "unit_revision_id", "currency"},
        "catalog.item_price_scope": {"subject_kind"},
        "catalog.item_price_series": {"item_id", "currency", "audience_kind"},
        "catalog.commercial_policy_scope": {"owner_id"},
    }
    readonly |= pricing_generated.get(entity_type, set())
    if entity_type.startswith("catalog.bulk_"):
        readonly |= set(context.native.fields)
    if entity_type == "catalog.item_price":
        # Published definitions are created only by the draft publication command.
        readonly |= set(context.native.fields)
    if entity_type in {"catalog.item", "catalog.product_family"}:
        readonly |= {"status", "structure_mode", "default_slot", "family_id"}
        if existing is not None and existing.status != "DRAFT":
            if "status" not in readable:
                raise PermissionDeniedError("product lifecycle is protected")
            editable = (
                {"name"} if entity_type == "catalog.item" else {"name", "description", "model_code"}
            )
            readonly |= set(context.native.fields) - editable
            writable_resource &= existing.status == "ACTIVE"
    if isinstance(existing, Item):
        family = await company_object(db, ProductFamily, existing.family_id, company_id=company_id)
        family_context = await load_field_context(db, current, company_id, "catalog.product_family")
        if "status" not in family_context.readable():
            raise PermissionDeniedError("product family lifecycle is protected")
        if family.status != "DRAFT" and existing.status != "DRAFT":
            readonly |= set(context.native.fields) - {"name"}
            writable_resource &= family.status == "ACTIVE"
        writable_resource &= family.status in {"DRAFT", "ACTIVE"}
    if entity_type in {"catalog.master_alias", "catalog.master_external_key"}:
        readonly |= {"entity_type", "target_id", "canonical_value", "normalization_version"}
        if not {"alias", "canonical_value"} <= readable:
            readable -= {"alias", "canonical_value"}
    if entity_type == "catalog.product_type_revision":
        readonly |= {"revision", "product_type_id", "kind", "published_at"}
        if operation == "create":
            readonly.discard("product_type_id")
        if operation == "publish":
            readonly.discard("published_at")
    if entity_type == "catalog.attribute_set_revision":
        readonly |= {"revision", "attribute_set_id", "published_at"}
        if operation == "publish":
            readonly.discard("published_at")
    if entity_type == "catalog.attribute_set_member":
        if operation != "publish":
            readonly |= {"revision_id"}
    if entity_type == "catalog.identifier_profile":
        readonly |= {"normalization_version"}
    if entity_type == "catalog.identifier_profile_requirement":
        readonly |= {"profile_id"}
    if entity_type == "catalog.inventory_profile_template_revision":
        readonly |= {"template_id", "revision", "published_at"}
    if entity_type == "catalog.manufacturing_operation_revision":
        readonly |= {"operation_id", "revision", "published_at", "status"}
    if entity_type == "catalog.manufacturing_route_revision":
        readonly |= {"route_id", "revision", "published_at", "status", "step_count"}
    if entity_type == "catalog.warranty_policy_revision":
        readonly |= {"policy_id", "revision", "published_at"}
    if entity_type == "catalog.return_policy_revision":
        readonly |= {"policy_id", "revision", "published_at", "condition_count"}
    if entity_type == "catalog.return_policy_condition" and operation != "publish":
        # Conditions belong to the parent revision aggregate; publication checks
        # their field authority, but an ordinary editor cannot reparent them.
        readonly.add("revision_id")
    if entity_type == "catalog.handling_profile_revision":
        readonly |= {"profile_id", "revision", "published_at"}
    if operation == "create":
        # The route assigns these links, but native creation checks their field authority.
        profile_parent = {
            "catalog.inventory_profile_template_revision": "template_id",
            "catalog.manufacturing_operation_revision": "operation_id",
            "catalog.manufacturing_route_revision": "route_id",
            "catalog.warranty_policy_revision": "policy_id",
            "catalog.return_policy_revision": "policy_id",
            "catalog.handling_profile_revision": "profile_id",
        }.get(entity_type)
        if profile_parent is not None:
            readonly.discard(profile_parent)
    if operation == "publish" and entity_type in PUBLISH_PERMISSIONS:
        readonly.discard("published_at")
        if entity_type in {
            "catalog.manufacturing_operation_revision",
            "catalog.manufacturing_route_revision",
        }:
            readonly.discard("status")
    if entity_type.startswith("catalog.product_configuration_") or entity_type in {
        "catalog.product_entry_option_policy",
        "catalog.product_numeric_default",
        "catalog.catalog_default_profile",
        "catalog.product_pricing_policy",
    }:
        readonly |= {
            "status",
            "owner_id",
            "latest_revision",
            "revision",
            "published_at",
            "source_draft_id",
            "draft_id",
            "revision_id",
            "preview_hash",
            "resolution_version",
            "policy_generation",
            "source_version",
        }
    if entity_type == "catalog.product_configuration_revision":
        readonly |= set(context.native.fields)
    if entity_type in {
        "catalog.family_group_assignment",
        "catalog.family_category",
        "catalog.family_manufacturer",
        "catalog.family_attribute",
        "catalog.family_attribute_option",
        "catalog.item_attribute_value",
        "catalog.item_variant_key",
        "catalog.item_unit_binding",
        "catalog.item_unit_revision",
        "catalog.item_barcode",
        "catalog.product_configuration_adoption",
        "catalog.product_configuration_adoption_source",
    }:
        readonly |= {
            "family_id",
            "item_id",
            "primary_slot",
            "combination_hash",
            "canonical_combination",
            "revision",
            "valid_to",
            "adoption_id",
        }
    effective = list(context.fields)
    if existing is not None:
        known = {field.key for field in effective if field.source == "custom"}
        for retired in context.definitions:
            if (
                not retired.is_active
                and retired.key not in known
                and (existing.custom_fields or {}).get(retired.key) is not None
            ):
                label = (
                    context.presentation.get(
                        "custom_field:" + retired.key, FieldPresentation()
                    ).label
                    or retired.key
                )
                effective.append(
                    EffectiveField(
                        "custom", retired.key, label, False, False, 32767, False, retired
                    )
                )
    fields = []
    for field in effective:
        key = field.key if field.source == "native" else "custom_field:" + field.key
        if key not in readable:
            continue
        presentation = context.presentation.get(key, FieldPresentation())
        definition = field.definition
        unavailable_condition = False
        if definition is not None:
            refs = (
                condition_fields(
                    definition.visibility,
                    allowed=frozenset(context.native.fields)
                    | {item.key for item in context.definitions},
                )
                if definition.visibility
                else frozenset()
            )
            refs = refs | ({definition.depends_on_key} if definition.depends_on_key else set())
            readable_refs = readable | {
                name.removeprefix("custom_field:")
                for name in readable
                if name.startswith("custom_field:")
            }
            unavailable_condition = not refs <= readable_refs
            if unavailable_condition:
                definition = definition.model_copy(
                    update={"visibility": None, "depends_on_key": None}
                )
        hint = (
            company_control(
                entity_type,
                field.key,
                configuration_control(entity_type, field.key),
                context.features,
            )
            if field.source == "native"
            else None
        )
        fields.append(
            FieldMetadata(
                key=field.key,
                source=field.source,
                label=field.label,
                required=field.required,
                visible=field.visible,
                order=field.order,
                writable=writable_resource
                and not unavailable_condition
                and field.writable
                and not (
                    definition is not None
                    and definition.is_immutable_after_create
                    and operation == "update"
                )
                and field.key not in readonly
                and resolve_field_effect(
                    rules, field_key=key, access="write", target=ScopePath(company_id=company_id)
                )
                != "deny",
                conditional_access=key in conditional or unavailable_condition,
                help_text=presentation.help_text
                or (
                    PRICING_HELP.get(field.key)
                    if entity_type == "catalog.product_pricing_policy"
                    else ENTRY_HELP.get(field.key)
                    if entity_type == "catalog.product_entry_option_policy"
                    else None
                ),
                placeholder=presentation.placeholder,
                display_group=presentation.display_group
                or (
                    "pricing_options"
                    if entity_type == "catalog.product_pricing_policy"
                    and field.key in PRICING_HELP
                    and field.key != "sale_level_count"
                    else "unit_conversion"
                    if entity_type == "catalog.product_entry_option_policy"
                    and field.key.removesuffix("_mode").removesuffix("_default") in UNIT_OPTIONS
                    else None
                ),
                suggested_value="false"
                if hint and hint.disabled_reason and hint.kind == "boolean"
                else presentation.suggested_value,
                custom=definition,
                control=hint,
            )
        )
    from catalog.tasks.field_adoption import state as adoption_state

    adopted = await adoption_state(db, company_id, entity_type) if product else None
    return FieldSet(
        adoption_version=adopted.row_version if adopted else 0,
        company_id=company_id,
        entity_type=entity_type,
        configuration_complete=set(context.native.fields) <= readable
        if entity_type.startswith("catalog.product_configuration_")
        or entity_type
        in {
            "catalog.product_entry_option_policy",
            "catalog.product_numeric_default",
            "catalog.catalog_default_profile",
            "catalog.product_pricing_policy",
        }
        else None,
        source_version=context.source_version,
        fields=fields,
    )
