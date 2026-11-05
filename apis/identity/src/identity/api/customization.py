"""Bounded company definition, layout and field-policy administration."""

from __future__ import annotations

import json
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import condition_fields, validate_definitions
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.features import FEATURES
from billing_platform.fields import assert_config_allowed, registry
from billing_platform.ids import uuid7
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.field_access import CompanyAccess
from identity.api.listing import paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.api.security import assignment_target
from identity.domain import accounting_fields, document_fields
from identity.domain.field_registry import COMPANY_RELATIONSHIP_FIELDS
from identity.models import (
    Company,
    CustomFieldDefinition,
    FieldConfig,
    FieldPolicy,
    Role,
    RoleAssignment,
    User,
    UserGroup,
    UserGroupMember,
)
from identity.schemas.base import Page, StrictModel
from identity.schemas.customization import (
    DefinitionItem,
    DefinitionListItem,
    DefinitionWrite,
    LayoutItem,
    LayoutWrite,
    PolicyItem,
    PolicyWrite,
)
from identity.services.audit import record
from identity.services.customization import (
    ENTITY,
    contract,
    definition_digest,
    definition_item,
    definitions,
    index_values,
    validate_contract,
)
from identity.services.field_delegation import (
    assert_field_delegation,
    field_definition,
    registered,
)

router = APIRouter(prefix="/v1", route_class=StrictRoute, responses=ERROR_RESPONSES)


async def definition_authority(db: AsyncSession, current: Actor, body: DefinitionWrite) -> None:
    target = ScopePath(company_id=body.company_id)
    current.require_scope("custom_field.manage", target=target)
    if body.company_id is not None:
        company = await db.get(Company, body.company_id)
        if company is None or company.status != "active":
            raise ValidationFailedError("definition company is unavailable")
    if body.requires_feature is not None and body.requires_feature not in FEATURES:
        raise ValidationFailedError("unknown required feature")
    await validate_contract(db, body.definition, body.entity_type)


async def save_definition(
    db: AsyncSession, current: Actor, body: DefinitionWrite, row: CustomFieldDefinition
) -> None:
    model = body.definition
    if row.key and (
        row.entity_type != body.entity_type
        or row.key != model.key
        or row.data_type != model.data_type
        or row.company_id != (body.company_id or SCOPE_ALL)
    ):
        raise ValidationFailedError("definition key, type and scope are immutable")
    existing = await definitions(db, body.company_id or SCOPE_ALL, body.entity_type)
    # A company override cannot weaken an existing logical field contract.
    for prior in existing:
        if prior.id != row.id and prior.key == model.key:
            old = contract(prior)
            if (
                old.data_type != model.data_type
                or old.validation.case_sensitive != model.validation.case_sensitive
                or (
                    old.validation.unique_within == "tenant"
                    and model.validation.unique_within != "tenant"
                )
            ):
                raise ValidationFailedError("override weakens the tenant definition")
    validate_definitions(
        (*(contract(d) for d in existing if d.key != model.key), model),
        native_fields=frozenset(
            registry.get(ENTITY).fields
            if body.entity_type == ENTITY
            else document_fields.contract(body.entity_type)["fields"]
        ),
        option_sources=frozenset()
        if body.entity_type == ENTITY
        else frozenset(document_fields.contract(body.entity_type)["option_sources"]),
    )
    if body.entity_type in document_fields.contracts():
        document_fields.validate_options(
            body.entity_type, (*(contract(d) for d in existing if d.key != model.key), model)
        )
    for key in [
        "entity_type",
        "label",
        "help_text",
        "placeholder",
        "display_order",
        "display_group",
        "requires_feature",
    ]:
        setattr(row, key, getattr(body, key))
    row.requires_adoption = body.entity_type in document_fields.contracts()
    row.company_id = body.company_id or SCOPE_ALL
    for key in [
        "key",
        "data_type",
        "is_active",
        "is_searchable",
        "is_immutable_after_create",
        "option_source_key",
        "depends_on_key",
        "visibility",
    ]:
        setattr(row, key, getattr(model, key))
    row.validation = model.validation.model_dump(mode="json")
    row.options = {"choices": [choice.model_dump() for choice in model.choices]}
    row.sequence_config = model.sequence_config.model_dump() if model.sequence_config else None
    row.default_value = json.dumps(model.default_value) if model.default_value is not None else None
    row.deactivated_at = None if model.is_active else utcnow()
    row.deactivated_by = None if model.is_active else current.user_id
    row.updated_by = current.user_id


@router.post("/custom-field-definitions", response_model=DefinitionItem, status_code=201)
async def create_definition(
    body: DefinitionWrite, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> DefinitionItem:
    await definition_authority(db, current, body)
    row = CustomFieldDefinition(id=uuid7(), tenant_id=current.tenant_id, created_by=current.user_id)
    # Reject adding required fields over existing records until data has been backfilled.
    if body.entity_type == ENTITY and (
        body.definition.validation.required or body.definition.default_value is not None
    ):
        stmt = select(Company.id)
        if body.company_id is not None:
            stmt = stmt.where(Company.id == body.company_id)
        if await db.scalar(stmt.limit(1)) is not None:
            raise ConflictError(
                "create an optional field, backfill values, then tighten validation"
            )
    await save_definition(db, current, body, row)
    db.add(row)
    record(
        db,
        current,
        action="custom_field.definition_created",
        entity="custom_field_definition",
        entity_id=row.id,
        company_id=body.company_id,
    )
    await db.flush()
    return definition_item(row)


@router.get("/custom-field-definitions", response_model=Page[DefinitionListItem])
async def list_definitions(
    request: Request,
    entity_type: str = ENTITY,
    company_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[DefinitionListItem]:
    if entity_type != ENTITY:
        document_fields.contract(entity_type)
    current.require_scope("custom_field.manage", target=ScopePath(company_id=company_id))
    return await paged(
        db,
        request,
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.entity_type == entity_type,
            CustomFieldDefinition.company_id.in_([SCOPE_ALL, company_id or SCOPE_ALL]),
        ),
        model=CustomFieldDefinition,
        schema=DefinitionListItem,
        limit=limit,
        cursor=cursor,
    )


@router.get("/custom-field-definitions/{definition_id}", response_model=DefinitionItem)
async def get_definition(
    definition_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> DefinitionItem:
    row = await db.get(CustomFieldDefinition, definition_id)
    if row is None or row.entity_type not in {ENTITY, *document_fields.contracts()}:
        raise NotFoundError("definition not found")
    current.require_scope(
        "custom_field.manage",
        target=ScopePath(company_id=None if row.company_id == SCOPE_ALL else row.company_id),
    )
    return definition_item(row)


@router.put("/custom-field-definitions/{definition_id}", response_model=DefinitionItem)
async def update_definition(
    definition_id: uuid.UUID,
    body: DefinitionWrite,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> DefinitionItem:
    row = await db.get(CustomFieldDefinition, definition_id)
    if row is None or row.entity_type not in {ENTITY, *document_fields.contracts()}:
        raise NotFoundError("definition not found")
    current.require_scope(
        "custom_field.manage",
        target=ScopePath(company_id=None if row.company_id == SCOPE_ALL else row.company_id),
    )
    await definition_authority(db, current, body)
    await db.refresh(row, with_for_update=True)
    if row.entity_type != ENTITY and body.expected_digest != definition_digest(row):
        raise ConflictError("definition changed; reload its digest before editing")
    before = contract(row)
    changed = body.definition.model_dump() != before.model_dump()
    if changed and row.entity_type == ENTITY:
        # Validate every affected stored value before changing its contract. Bounded work;
        # large tenants must use reviewed backfill/rebuild commands, never a partial scan.
        stmt = select(Company)
        if row.company_id != SCOPE_ALL:
            stmt = stmt.where(Company.id == row.company_id)
        companies = list(await db.scalars(stmt.limit(201)))
        if len(companies) > 200:
            raise ConflictError("definition change requires a bounded migration job")
        from billing_platform.custom_fields import scalar_value
        from billing_platform.db.reference_models import Currency

        currencies = frozenset(await db.scalars(select(Currency.code)))
        for company in companies:
            value = (company.custom_fields or {}).get(row.key)
            if body.definition.validation.required and value is None:
                raise ConflictError("backfill existing company values before requiring this field")
            if value is not None:
                if body.definition.sequence_config != before.sequence_config:
                    raise ConflictError("a used sequence configuration is immutable")
                try:
                    scalar_value(body.definition, value, currencies=currencies)
                except (ValueError, TypeError) as exc:
                    raise ValidationFailedError(
                        "existing values do not satisfy the new definition"
                    ) from exc
    await save_definition(db, current, body, row)
    if changed and row.entity_type == ENTITY:
        # Rebuild the bounded affected set in the same transaction as its new contract.
        # No observer can read a partially changed index or uniqueness rule.
        from sqlalchemy import delete

        from identity.models import CustomFieldValueIndex

        await db.execute(
            delete(CustomFieldValueIndex).where(CustomFieldValueIndex.definition_id == row.id)
        )
        await db.flush()
        for company in companies:
            await index_values(
                db, company, await definitions(db, company.id), company.custom_fields or {}
            )
    record(
        db,
        current,
        action="custom_field.definition_updated",
        entity="custom_field_definition",
        entity_id=row.id,
        company_id=body.company_id,
    )
    await db.flush()
    return definition_item(row)


@router.put("/entities/{entity_type}/field-config/{field_key}", response_model=LayoutItem)
async def configure_field(
    entity_type: str,
    field_key: str,
    body: LayoutWrite,
    company_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> FieldConfig:
    if company_id is not None and entity_type not in document_fields.contracts():
        raise ValidationFailedError("company layouts are supported for product fields")
    current.require_scope("field_config.manage", target=ScopePath(company_id=company_id))
    if company_id is not None:
        company = await db.get(Company, company_id)
        if company is None or company.status != "active":
            raise ValidationFailedError("layout company is unavailable")
    definition = await field_definition(db, field_key, entity_type, company_id)
    if definition is None:
        native = (
            (registry.get(ENTITY).fields | COMPANY_RELATIONSHIP_FIELDS)[field_key]
            if entity_type == ENTITY
            else document_fields.native_field(entity_type, field_key)
            if entity_type in document_fields.contracts()
            else accounting_fields.native_field(entity_type, field_key)
        )
        assert_config_allowed(
            native,
            field_key=field_key,
            is_visible=body.is_visible,
            is_required=body.is_required,
            label_override=body.label_override,
        )
    elif body.is_required is False and contract(definition).validation.required:
        raise ValidationFailedError("layout cannot weaken field requiredness")
    if body.is_required is True:
        raise ValidationFailedError(
            "requiredness is managed through definition validation and existing-data checks"
        )
    if definition is not None and entity_type in document_fields.contracts():
        field_key = definition.key
    row = await db.scalar(
        select(FieldConfig).where(
            FieldConfig.company_id == (company_id or SCOPE_ALL),
            FieldConfig.entity_type == entity_type,
            FieldConfig.field_key == field_key,
        )
    )
    if row is None:
        row = FieldConfig(
            id=uuid7(),
            tenant_id=current.tenant_id,
            company_id=company_id or SCOPE_ALL,
            entity_type=entity_type,
            field_key=field_key,
            field_source="custom" if definition else "native",
            definition_id=definition.id if definition else None,
            created_by=current.user_id,
        )
        db.add(row)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.updated_by = current.user_id
    record(db, current, action="field_config.updated", entity="field_config", entity_id=row.id)
    await db.flush()
    return row


@router.get("/entities/{entity_type}/field-config", response_model=Page[LayoutItem])
async def layouts(
    entity_type: str,
    request: Request,
    company_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[LayoutItem]:
    current.require_scope("field_config.manage", target=ScopePath(company_id=company_id))
    if company_id is not None and entity_type not in document_fields.contracts():
        raise ValidationFailedError("company layouts are supported for product fields")
    if entity_type != ENTITY:
        (
            document_fields if entity_type in document_fields.contracts() else accounting_fields
        ).contract(entity_type)
    return await paged(
        db,
        request,
        select(FieldConfig).where(
            FieldConfig.entity_type == entity_type,
            FieldConfig.company_id.in_([SCOPE_ALL, company_id or SCOPE_ALL]),
        ),
        model=FieldConfig,
        schema=LayoutItem,
        limit=limit,
        cursor=cursor,
    )


async def guard_policy(db: AsyncSession, current: Actor, body: PolicyWrite) -> None:
    target = await assignment_target(db, body.scope_type, body.scope_id)
    await assert_field_delegation(
        db,
        current,
        entity_type=body.entity_type,
        field_key=body.field_key,
        access=body.access,
        target=target,
    )
    subjects = {"user": User, "role": Role, "user_group": UserGroup}
    subject = await db.get(subjects[body.subject_type], body.subject_id)
    if subject is None:
        raise ValidationFailedError("policy subject does not exist")
    groups = set(
        await db.scalars(
            select(UserGroupMember.user_group_id).where(UserGroupMember.user_id == current.user_id)
        )
    )
    groups.update(current.group_ids)
    if (body.subject_type == "user" and body.subject_id == current.user_id) or (
        body.subject_type == "user_group" and body.subject_id in groups
    ):
        raise PermissionDeniedError("you cannot edit your own field access")
    if body.subject_type == "role":
        membership = await db.scalar(
            select(RoleAssignment.id)
            .where(
                RoleAssignment.role_id == body.subject_id,
                RoleAssignment.is_active.is_(True),
                or_(
                    (RoleAssignment.subject_type == "user")
                    & (RoleAssignment.subject_id == current.user_id),
                    (RoleAssignment.subject_type == "user_group")
                    & RoleAssignment.subject_id.in_(groups),
                ),
            )
            .limit(1)
        )
        if membership is not None:
            raise PermissionDeniedError("you cannot edit policies on a role assigned to you")
    if body.condition is not None:
        # Policy conditions use native fields; custom visibility has its own validator.
        fields = (
            registry.get(ENTITY).fields
            if body.entity_type == ENTITY
            else (
                document_fields
                if body.entity_type in document_fields.contracts()
                else accounting_fields
            ).contract(body.entity_type)["fields"]
        )
        condition_fields(body.condition, allowed=frozenset(fields))


def policy_item(row: FieldPolicy) -> PolicyItem:
    return PolicyItem.model_validate(
        {key: getattr(row, key) for key in PolicyItem.model_fields if key != "scope_id"}
        | {"scope_id": None if row.scope_id == SCOPE_ALL else row.scope_id}
    )


@router.post("/field-policies", response_model=PolicyItem, status_code=201)
async def create_policy(
    body: PolicyWrite, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> PolicyItem:
    await guard_policy(db, current, body)
    row = FieldPolicy(
        id=uuid7(),
        tenant_id=current.tenant_id,
        **body.model_dump(exclude={"scope_id"}),
        scope_id=body.scope_id or SCOPE_ALL,
        created_by=current.user_id,
        updated_by=current.user_id,
    )
    db.add(row)
    record(
        db,
        current,
        action="field_policy.created",
        entity="field_policy",
        entity_id=row.id,
        company_id=body.scope_id,
        reason=body.reason,
    )
    await db.flush()
    return policy_item(row)


@router.put("/field-policies/{policy_id}", response_model=PolicyItem)
async def update_policy(
    policy_id: uuid.UUID,
    body: PolicyWrite,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> PolicyItem:
    row = await db.get(FieldPolicy, policy_id)
    if row is None or not registered(row.entity_type):
        raise NotFoundError("policy not found")
    before = policy_item(row)
    identity_fields = {
        "subject_type",
        "subject_id",
        "entity_type",
        "field_key",
        "access",
        "scope_type",
        "scope_id",
    }
    if any(getattr(body, k) != getattr(before, k) for k in identity_fields):
        raise ValidationFailedError("policy subject, field and scope are immutable")
    await guard_policy(db, current, body)
    row.effect, row.condition, row.reason, row.is_active = (
        body.effect,
        body.condition,
        body.reason,
        body.is_active,
    )
    row.updated_by = current.user_id
    row.deactivated_at = None if body.is_active else utcnow()
    row.deactivated_by = None if body.is_active else current.user_id
    changes: dict[str, Any] = {
        "is_active": {"from": before.is_active, "to": row.is_active},
        "effect": {"from": before.effect, "to": row.effect},
    }
    if before.condition != row.condition:
        # Narrowing a deny's condition relaxes it as surely as flipping the effect, so
        # the change has to be visible. The clause itself can name a business value, so
        # it is recorded as a changed-field marker rather than stored (§6.9).
        changes["condition"] = {"from": before.condition, "to": row.condition}
    record(
        db,
        current,
        action="field_policy.updated",
        entity="field_policy",
        entity_id=row.id,
        company_id=body.scope_id,
        reason=body.reason,
        changes=changes,
    )
    await db.flush()
    return policy_item(row)


@router.get("/field-policies", response_model=Page[PolicyItem])
async def policies(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    entity_type: str = ENTITY,
    company_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[PolicyItem]:
    if company_id is not None and entity_type not in document_fields.contracts():
        raise ValidationFailedError("company policy listing is supported for products")
    current.require_scope("field_policy.manage", target=ScopePath(company_id=company_id))
    if entity_type != ENTITY:
        (
            document_fields if entity_type in document_fields.contracts() else accounting_fields
        ).contract(entity_type)
    from billing_platform.pagination import PageRequest

    from identity.api.listing import cursor_codec, keyset_page
    from identity.schemas.base import PageMeta

    statement = select(FieldPolicy).where(FieldPolicy.entity_type == entity_type)
    if company_id is not None:
        statement = statement.where(
            or_(
                (FieldPolicy.scope_type == "tenant") & (FieldPolicy.scope_id == SCOPE_ALL),
                (FieldPolicy.scope_type == "company") & (FieldPolicy.scope_id == company_id),
            )
        )
    rows, next_cursor, more = await keyset_page(
        db,
        statement,
        model=FieldPolicy,
        projection=PolicyItem,
        page=PageRequest(limit, cursor),
        sort="id",
        allowed=frozenset({"id"}),
        default="id",
        codec=cursor_codec(request, "field-policies"),
    )
    return Page(
        items=[policy_item(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=more),
    )


class RebuildRequest(StrictModel):
    after: uuid.UUID | None = None
    definition_hash: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    apply_defaults: bool = False


class RebuildResult(StrictModel):
    processed: int
    next_after: uuid.UUID | None
    definition_hash: str


@router.post("/custom-field-definitions/{definition_id}/rebuild", response_model=RebuildResult)
async def rebuild_definition(
    definition_id: uuid.UUID,
    body: RebuildRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> RebuildResult:
    import hashlib

    from billing_platform.idempotency import canonical_json

    from identity.services.customization import prepare_values

    row = await db.get(CustomFieldDefinition, definition_id)
    if row is None or row.entity_type not in {ENTITY, *document_fields.contracts()}:
        raise NotFoundError("definition not found")
    if row.entity_type != ENTITY:
        raise ValidationFailedError("use Catalog product field adoption and bulk value commands")
    target = ScopePath(company_id=None if row.company_id == SCOPE_ALL else row.company_id)
    current.require_scope("custom_field.manage", target=target)
    current.require_scope("company.update", target=target)
    fingerprint = hashlib.sha256(
        canonical_json(definition_item(row).model_dump(mode="json"))
    ).hexdigest()
    if (body.after is not None and body.definition_hash is None) or (
        body.definition_hash is not None and body.definition_hash != fingerprint
    ):
        raise ConflictError("definition changed; restart the rebuild")
    query = select(Company).order_by(Company.id)
    if row.company_id != SCOPE_ALL:
        query = query.where(Company.id == row.company_id)
    if body.after is not None:
        query = query.where(Company.id > body.after)
    companies = list(await db.scalars(query.limit(body.limit + 1)))
    more = len(companies) > body.limit
    companies = companies[: body.limit]
    access = await CompanyAccess.load(db, current)
    for company in companies:
        effective = await definitions(db, company.id)
        supplied = {}
        if (
            body.apply_defaults
            and row.id in {d.id for d in effective}
            and row.key not in (company.custom_fields or {})
        ):
            default = contract(row).default_value
            if default is not None:
                supplied[row.key] = default
        if supplied:
            access.assert_write(company, {"custom_fields": supplied})
            company.custom_fields = await prepare_values(
                db,
                company,
                supplied,
                creating=False,
                readable=frozenset(registry.get(ENTITY).fields),
            )
            company.updated_by = current.user_id
        else:
            await index_values(db, company, effective, company.custom_fields or {})
    if companies:
        record(
            db,
            current,
            action="custom_field.index_rebuilt",
            entity="custom_field_definition",
            entity_id=row.id,
            company_id=target.company_id,
            changes={"processed": {"to": len(companies)}},
        )
    return RebuildResult(
        processed=len(companies),
        next_after=companies[-1].id if more else None,
        definition_hash=fingerprint,
    )


@router.get("/entities/{entity_type}/custom-field-contract")
async def product_field_contract(
    entity_type: str, company_id: uuid.UUID | None = None, current: Actor = Depends(actor)
) -> dict[str, object]:
    current.require_scope("custom_field.manage", target=ScopePath(company_id=company_id))
    return {"version": 1, **document_fields.contract(entity_type)}
