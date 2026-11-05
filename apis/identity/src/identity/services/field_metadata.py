"""Merged native/custom descriptors, layout and effective read/write policy."""

from __future__ import annotations

import uuid
from functools import cache
from typing import Any, TypedDict

from billing_platform.authz import ScopePath, has_permission
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, ValidationFailedError
from billing_platform.field_policy import denied_fields
from billing_platform.fields import registry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.api.field_access import CompanyAccess
from identity.domain.company_immutability import IMMUTABLE_AFTER_POSTING
from identity.domain.field_registry import COMPANY_RELATIONSHIP_FIELDS
from identity.models import Company, CompanyFeature, FieldConfig, PostingReservation
from identity.schemas.company import CompanyCreate, CompanyUpdate, FieldDescriptor, FieldSet
from identity.services.customization import ENTITY, contract, definitions


class NativeContract(TypedDict):
    data_type: str
    validation: dict[str, Any]
    choices: list[dict[str, Any]] | None


@cache
def native_contract(key: str) -> NativeContract:
    """Expose validated input types and bounds, without duplicating the form schema."""
    from identity.models import (
        BUSINESS_NATURES,
        CURRENCY_SYMBOL_POSITIONS,
        DIGIT_GROUPINGS,
        ENTITY_TYPES,
        NEGATIVE_FORMATS,
        ROUNDING_MODES,
        TAX_TREATMENTS,
        VISIBILITIES,
    )

    prop = CompanyCreate.model_json_schema()["properties"].get(key, {})
    variants = prop.get("anyOf", [prop])
    scalar: dict[str, Any] = next((p for p in variants if p.get("type") != "null"), {})
    kind = scalar.get("type", "string")
    if key in {"credit_limit_default", "cash_receipt_limit"}:
        kind = "decimal"
    elif scalar.get("format") == "date":
        kind = "date"
    elif key in {"terms_and_conditions", "declaration_text"}:
        kind = "long_text"
    choices = {
        "entity_type": ENTITY_TYPES,
        "rounding_mode": ROUNDING_MODES,
        "business_nature": BUSINESS_NATURES,
        "tax_treatment_default": TAX_TREATMENTS,
        "digit_grouping": DIGIT_GROUPINGS,
        "negative_format": NEGATIVE_FORMATS,
        "currency_symbol_position": CURRENCY_SYMBOL_POSITIONS,
        "visibility": VISIBILITIES,
    }.get(key)
    return {
        "data_type": kind,
        "validation": {
            "nullable": any(p.get("type") == "null" for p in variants),
            **{
                name: scalar[source]
                for name, source in {
                    "min_length": "minLength",
                    "max_length": "maxLength",
                    "min": "minimum",
                    "max": "maximum",
                    "pattern": "pattern",
                }.items()
                if source in scalar
            },
        },
        "choices": [
            {"value": v, "label": v.replace("_", " ").capitalize()} for v in sorted(choices)
        ]
        if choices
        else None,
    }


async def company_field_set(
    db: AsyncSession, current: Actor, entity_type: str, company_id: uuid.UUID | None
) -> FieldSet:
    if entity_type != ENTITY:
        raise NotFoundError("no field set for this entity type")
    target = ScopePath(company_id=company_id)
    # Creation metadata contains no company data; a create-only tenant actor needs it too.
    if company_id is None and has_permission(
        current.grants, "company.create", target=target, on_date=utcnow().date()
    ):
        current.require_scope("company.create", target=target)
    else:
        current.require_scope("company.read", target=target)
    company = await db.get(Company, company_id) if company_id else None
    if company_id is not None and company is None:
        raise NotFoundError("company not found")
    features = (
        frozenset(
            await db.scalars(
                select(CompanyFeature.feature_key).where(
                    CompanyFeature.company_id == company_id, CompanyFeature.is_enabled.is_(True)
                )
            )
        )
        if company_id
        else frozenset()
    )
    native = registry.get(ENTITY)
    fields = {
        key: FieldDescriptor(
            key=key,
            required=value.required,
            hideable=value.hideable,
            renameable=value.renameable,
            requires_feature=value.requires_feature,
            group=value.group,
            order=value.order,
            label=key,
            **native_contract(key),
        )
        for key, value in (native.fields | COMPANY_RELATIONSHIP_FIELDS).items()
        if company_id is None
        or value.requires_feature is None
        or value.requires_feature in features
    }
    for definition in await definitions(db, company_id or SCOPE_ALL):
        if not definition.is_active or (
            definition.requires_feature and definition.requires_feature not in features
        ):
            continue
        model = contract(definition)
        key = "custom_field:" + definition.key
        fields[key] = FieldDescriptor(
            custom=model,
            key=key,
            source="custom",
            label=definition.label,
            help_text=definition.help_text,
            placeholder=definition.placeholder,
            default_value=model.default_value,
            required=model.validation.required,
            hideable=not model.validation.required,
            renameable=True,
            requires_feature=definition.requires_feature,
            group=definition.display_group or "custom",
            order=definition.display_order,
            writable=model.data_type != "auto_number"
            and not (company is not None and model.is_immutable_after_create),
            data_type=model.data_type,
            validation=model.validation.model_dump(mode="json"),
            choices=[c.model_dump() for c in model.choices],
        )
    layouts = list(
        await db.scalars(
            select(FieldConfig)
            .where(FieldConfig.entity_type == ENTITY, FieldConfig.company_id == SCOPE_ALL)
            .limit(1025)
        )
    )
    if len(layouts) > 1024:
        raise ValidationFailedError("field configuration exceeds resolution bound")
    for layout in layouts:
        field = fields.get(layout.field_key)
        if field is None:
            continue
        updates = {
            key: value
            for key, value in {
                "label": layout.label_override,
                "is_visible": layout.is_visible,
                "required": layout.is_required,
                "order": layout.display_order,
                "group": layout.display_group,
            }.items()
            if value is not None
        }
        fields[layout.field_key] = field.model_copy(update=updates)
    access = await CompanyAccess.load(db, current)
    rules = access.rules(target, access.values(company) if company else None)
    hidden = denied_fields(fields, rules=rules, access="read", target=target)
    readonly = denied_fields(fields, rules=rules, access="write", target=target)
    can_write = has_permission(
        current.grants,
        "company.update" if company else "company.create",
        target=target,
        on_date=utcnow().date(),
    )
    if company and company.status != "active":
        can_write = False
    frozen = bool(company and company.first_posted_at)
    if company and not frozen:
        frozen = (
            await db.scalar(
                select(PostingReservation.id)
                .where(
                    PostingReservation.company_id == company.id,
                    PostingReservation.status == "pending",
                )
                .limit(1)
            )
            is not None
        )
    editable = (CompanyUpdate if company else CompanyCreate).model_fields
    readonly_keys = set(readonly) | {
        key
        for key in fields
        if not can_write
        or (frozen and key in IMMUTABLE_AFTER_POSTING)
        or (not key.startswith("custom_field:") and key not in editable)
    }
    result = [
        value.model_copy(update={"writable": False}) if key in readonly_keys else value
        for key, value in fields.items()
        if key not in hidden
    ]
    return FieldSet(
        entity_type=ENTITY,
        model_name=native.model_name,
        fields=sorted(result, key=lambda f: (f.order, f.key)),
    )
