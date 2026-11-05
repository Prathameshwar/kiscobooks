"""Company-scoped voucher foundation endpoints."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.idempotency import CommandReceipt
from billing_platform.schema import resolved_schema
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock import STOCK_PROFILES

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.domain.print_capabilities import MANIFEST_VERSION, MANIFESTS
from vouchers.domain.registry import FOUNDATION_SECTIONS, KINDS, REGISTRY_VERSION
from vouchers.models import core as m
from vouchers.models.counter import CheckoutCounter, CounterOutlet
from vouchers.schemas.configuration import (
    BindingCreate,
    ClassCreate,
    ConfigurationCreate,
    Contract,
    Policy,
    TypeCreate,
    TypeRevise,
    Version,
)
from vouchers.schemas.documents import (
    IssueRequest,
    SeriesCreate,
    TemplateCreate,
    VoucherActionRequest,
    VoucherEdit,
    VoucherInput,
)
from vouchers.schemas.reads import ListQuery, ResourceDetail, ResourcePage, VoucherDetail
from vouchers.tasks import administration as admin
from vouchers.tasks import documents, notifications, reads
from vouchers.tasks.access import authorize, denied, visible_custom_keys
from vouchers.tasks.common import audit, command, expected, get
from vouchers.tasks.configuration import effective

router = APIRouter(
    prefix="/v1/companies/{company_id}", responses=ERRORS, dependencies=[Depends(unique_query)]
)
RESOURCES = {
    "voucher-types": m.VoucherType,
    "voucher-classes": m.VoucherClass,
    "voucher-type-revisions": m.VoucherTypeRevision,
    "voucher-configuration-revisions": m.VoucherConfigurationRevision,
    "voucher-configurations": m.VoucherConfigurationProfile,
    "voucher-series": m.VoucherNumberSeries,
    "voucher-templates": m.VoucherTemplate,
    "vouchers": m.Voucher,
    "counter-outlets": CounterOutlet,
    "checkout-counters": CheckoutCounter,
}


@router.get("/print-capabilities")
async def print_capabilities(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> dict[str, Any]:
    """What each kind's printer prints from a designed layout; the designer blocks the rest."""
    authorize(current, "read")
    return {"version": MANIFEST_VERSION, "kinds": list(MANIFESTS.values())}


@router.get("/voucher-capabilities")
async def capabilities(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> dict[str, Any]:
    authorize(current, "read")
    enabled = request.app.state.settings.money_execution_enabled
    invoices_enabled = request.app.state.settings.invoice_execution_enabled
    stock_enabled = bool(
        request.app.state.settings.stock_execution_enabled
        and request.app.state.settings.stock_execution_owner
    )
    # A goods Purchase bill (B24) posts stock and invoice together, so it needs both releases.
    physical = tuple(
        profile
        for action, profile in STOCK_PROFILES.items()
        if action != "PURCHASE_INVOICE" or invoices_enabled
    )
    return {
        "registry_version": REGISTRY_VERSION,
        "checkpoint": "C1_ORDINARY_MONEY" if enabled else "C0_FOUNDATION",
        "financial_execution": enabled,
        "invoice_execution": invoices_enabled,
        "purchase_supporting_files": bool(request.app.state.settings.supporting_file_root),
        "stock_execution": stock_enabled,
        "activation_ready": False,
        "kinds": [
            {
                "kind": k.code,
                "family": k.family,
                "profiles": list(k.profiles),
                "draft_sections": sorted(k.sections & FOUNDATION_SECTIONS),
                "planned_sections": sorted(k.sections),
                "execution_ready": (
                    enabled and k.code in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}
                )
                or (
                    invoices_enabled
                    and k.code in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"}
                )
                or (stock_enabled and any(kind == k.code for kind, _ in physical)),
                "stock_execution_profiles": sorted(
                    profile for kind, profile in physical if kind == k.code and stock_enabled
                ),
                "blocking_batch": k.effect_batch,
            }
            for k in KINDS
        ],
        "settings_schema": resolved_schema(Policy),
    }


@router.get("/voucher-kinds")
async def kinds(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> dict[str, Any]:
    return await capabilities(company_id, request, current)


@router.post("/voucher-types", response_model=ResourceDetail, status_code=201)
async def create_type(
    company_id: uuid.UUID,
    body: TypeCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await administrative_create(
        request, current, "type.manage", idempotency_key, body, admin.type_create, m.VoucherType
    )


@router.post("/voucher-configurations", response_model=ResourceDetail, status_code=201)
async def create_configuration(
    company_id: uuid.UUID,
    body: ConfigurationCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await administrative_create(
        request,
        current,
        "configuration.manage",
        idempotency_key,
        body,
        admin.configuration_create,
        m.VoucherConfigurationProfile,
    )


@router.post("/voucher-series", response_model=ResourceDetail, status_code=201)
async def create_series(
    company_id: uuid.UUID,
    body: SeriesCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await administrative_create(
        request,
        current,
        "series.manage",
        idempotency_key,
        body,
        admin.series_create,
        m.VoucherNumberSeries,
    )


@router.post("/voucher-templates", response_model=ResourceDetail, status_code=201)
async def create_template(
    company_id: uuid.UUID,
    body: TemplateCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await administrative_create(
        request,
        current,
        "template.manage",
        idempotency_key,
        body,
        admin.template_create,
        m.VoucherTemplate,
    )


async def administrative_create(
    request: Request, current: Access, permission: str, key: str, body: Any, create: Any, model: Any
) -> JSONResponse:
    if denied(current, "vouchers.configuration", set(type(body).model_fields), "write"):
        raise PermissionDeniedError("configuration fields are not writable")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await create(db, current, body)
        await db.flush()
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await admin.detail(db, current, model, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory, current, permission, key, body, mutate, render
        )
    )


@router.post("/voucher-types/{object_id}/revisions", response_model=ResourceDetail)
async def revise_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: TypeRevise,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await administrative_revise(
        request,
        current,
        "type.manage",
        idempotency_key,
        object_id,
        body,
        admin.type_revise,
        m.VoucherType,
    )


@router.post("/voucher-configurations/{object_id}/revisions", response_model=ResourceDetail)
async def revise_configuration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: TypeRevise,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await administrative_revise(
        request,
        current,
        "configuration.manage",
        idempotency_key,
        object_id,
        body,
        admin.configuration_revise,
        m.VoucherConfigurationProfile,
    )


async def administrative_revise(
    request: Request,
    current: Access,
    permission: str,
    key: str,
    object_id: uuid.UUID,
    body: Any,
    revise: Any,
    model: Any,
) -> JSONResponse:
    if denied(current, "vouchers.configuration", set(type(body).model_fields), "write"):
        raise PermissionDeniedError("configuration fields are not writable")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await revise(db, current, object_id, body)
        await db.flush()
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await admin.detail(db, current, model, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            permission,
            key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.post("/voucher-configurations/{object_id}/publish", response_model=ResourceDetail)
async def publish_configuration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: Version,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    if denied(current, "vouchers.configuration", {"policy", "status"}, "write"):
        raise PermissionDeniedError("configuration fields are not writable")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await get(db, current, m.VoucherConfigurationProfile, object_id, lock=True)
        expected(row, body.expected_version)
        revision = await db.scalar(
            select(m.VoucherConfigurationRevision).where(
                m.VoucherConfigurationRevision.company_id == company_id,
                m.VoucherConfigurationRevision.profile_id == row.id,
                m.VoucherConfigurationRevision.revision_number == row.current_revision,
            )
        )
        if revision is None or revision.status != "DRAFT" or row.status != "ACTIVE":
            raise ConflictError("configuration revision cannot be published")
        await admin.validate_policy_references(db, current, Policy.model_validate(revision.policy))
        revision.status = "PUBLISHED"
        row.row_version += 1
        audit(db, current, "configuration", row.id, "publish")
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await admin.detail(db, current, m.VoucherConfigurationProfile, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.publish",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.post("/voucher-types/{object_id}/configuration-bindings")
async def type_bind(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BindingCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await bind_configuration(request, current, object_id, body, idempotency_key)


@router.post("/voucher-configuration-bindings")
async def company_bind(
    company_id: uuid.UUID,
    body: BindingCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await bind_configuration(request, current, None, body, idempotency_key)


async def bind_configuration(
    request: Request, current: Access, type_id: uuid.UUID | None, body: BindingCreate, key: str
) -> JSONResponse:
    if denied(current, "vouchers.configuration", {"policy", "status"}, "write"):
        raise PermissionDeniedError("configuration fields are not writable")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await admin.bind(db, current, type_id, body)
        await db.flush()
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, m.VoucherConfigurationBinding, uuid.UUID(refs["id"]))
        return {"id": str(row.id), "configuration_revision_id": str(row.configuration_revision_id)}

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            key,
            body,
            mutate,
            render,
            object_id=type_id,
        )
    )


@router.post("/voucher-types/{object_id}/classes", response_model=ResourceDetail, status_code=201)
async def create_class(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ClassCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    if denied(current, "vouchers.configuration", {"policy", "status"}, "write"):
        raise PermissionDeniedError("configuration fields are not writable")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await admin.class_create(db, current, object_id, body)
        await db.flush()
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await admin.detail(db, current, m.VoucherClass, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "type.manage",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.get("/voucher-types/{object_id}/effective-configuration")
async def effective_configuration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    date: dt.date,
    class_id: uuid.UUID | None = None,
    posting_date: dt.date | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    authorize(current, "read")
    row = await get(db, current, m.VoucherType, object_id)
    revision = await db.scalar(
        select(m.VoucherTypeRevision).where(
            m.VoucherTypeRevision.company_id == company_id,
            m.VoucherTypeRevision.type_id == row.id,
            m.VoucherTypeRevision.revision_number == row.current_revision,
        )
    )
    if revision is None:
        raise ConflictError("type revision unavailable")
    if denied(current, "vouchers.configuration", set(Policy.model_fields), "read"):
        raise PermissionDeniedError("configuration is not readable")
    _, evidence = await effective(
        db, current, revision.id, date=date, posting_date=posting_date, class_id=class_id
    )
    return evidence


@router.get("/voucher-types/{object_id}/field-set")
async def field_set(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    date: dt.date,
    class_id: uuid.UUID | None = None,
    posting_date: dt.date | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    evidence = await effective_configuration(
        company_id, object_id, date, class_id, posting_date, current, db
    )
    return await native_field_set(db, current, company_id, evidence)


async def native_field_set(
    db: AsyncSession, current: Access, company_id: uuid.UUID, evidence: dict[str, Any]
) -> dict[str, Any]:
    """The native schema, visible custom fields and effective configuration an editor works from.

    Shared by the type's field-set (for a new voucher) and a saved voucher's (for editing it), so
    the two can never describe different forms.
    """
    schema = resolved_schema(VoucherInput)
    from vouchers.tasks.stock_details import protect_schema

    protect_schema(current, schema)
    blocked = denied(current, "vouchers.voucher", set(schema["properties"]), "read")
    schema["properties"] = {
        key: value for key, value in schema["properties"].items() if key not in blocked
    }
    schema["required"] = [key for key in schema.get("required", []) if key not in blocked]
    for key, entry in schema["properties"].items():
        entry["readOnly"] = bool(denied(current, "vouchers.voucher", {key}, "write"))
    item_schema = (
        schema.get("properties", {})
        .get("lines", {})
        .get("items", {})
        .get("properties", {})
        .get("item", {})
    )
    item_properties = item_schema.get("properties", {})
    item_blocked = denied(current, "vouchers.voucher_item", set(item_properties), "read")
    item_schema["properties"] = {
        key: entry | {"readOnly": bool(denied(current, "vouchers.voucher_item", {key}, "write"))}
        for key, entry in item_properties.items()
        if key not in item_blocked
    }
    item_schema["required"] = [
        key for key in item_schema.get("required", []) if key not in item_blocked
    ]
    customs = []
    resolved = Policy.model_validate(evidence["policy"])
    projections = list(
        await db.scalars(
            select(m.VoucherDefinitionProjection)
            .where(m.VoucherDefinitionProjection.company_id == company_id)
            .limit(257)
        )
    )
    candidates = []
    for row in projections:
        allowed = (
            resolved.header_field_keys
            if row.entity_type == "vouchers.voucher"
            else resolved.item_field_keys
        )
        if allowed is None or row.field_key in allowed:
            candidates.append(row)
    visible_keys = {
        entity: visible_custom_keys(
            current, entity, [row.definition for row in candidates if row.entity_type == entity]
        )
        for entity in ("vouchers.voucher", "vouchers.voucher_item")
    }
    if "lines" in blocked:
        visible_keys["vouchers.voucher_item"] = set()
    for row in candidates:
        if row.field_key in visible_keys[row.entity_type]:
            customs.append(
                {
                    "entity_type": row.entity_type,
                    "definition": row.definition,
                    "presentation": row.presentation,
                    "source_version": row.source_version,
                    "readOnly": bool(
                        denied(current, row.entity_type, {row.field_key, "custom_fields"}, "write")
                    ),
                }
            )
    public_policy = dict(evidence["policy"])
    for entity, names in (
        ("vouchers.voucher", ("header_field_keys", "required_header_fields")),
        ("vouchers.voucher_item", ("item_field_keys", "required_item_fields")),
    ):
        for name in names:
            if public_policy.get(name) is not None:
                public_policy[name] = sorted(set(public_policy[name]) & visible_keys[entity])
    return {
        "native": schema,
        "custom": customs,
        "configuration": evidence | {"policy": public_policy},
        "layouts": [
            layout
            for layout in current.context.layouts
            if layout.get("entity_type") in visible_keys
            and isinstance(layout.get("field_key"), str)
            and (
                layout.get("field_key") in visible_keys[layout["entity_type"]]
                if layout["field_key"].startswith("cf_")
                else not denied(current, layout["entity_type"], {layout["field_key"]}, "read")
            )
        ],
    }


@router.get("/vouchers/{object_id}/field-set")
async def voucher_field_set(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    revision_id: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    """Pinned custom-field definitions for a saved revision, plus its edit view.

    Everything is filtered by current read policy. `native`, `custom`, `configuration` and `layouts`
    are the type's field-set for this voucher's dates, so a client can edit what it reopened.
    """
    authorize(current, "read")
    voucher = await get(db, current, m.Voucher, object_id)
    revision = (
        await get(db, current, m.VoucherRevision, revision_id)
        if revision_id is not None
        else await documents.revision_for(db, current, voucher)
    )
    if revision.voucher_id != voucher.id:
        raise NotFoundError("voucher revision unavailable")
    snapshot = revision.definition_snapshot
    presentations = snapshot.get("presentation", {})

    def visible(entity: str, definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keys = visible_custom_keys(current, entity, definitions)
        return [
            {
                "definition": definition,
                "presentation": presentations.get(entity + ":" + definition["key"], {}),
            }
            for definition in definitions
            if definition["key"] in keys
        ]

    items = (
        {
            key: visible("vouchers.voucher_item", definitions)
            for key, definitions in snapshot.get("items", {}).items()
        }
        if not denied(current, "vouchers.voucher", {"lines"}, "read")
        else {}
    )
    pinned = {
        "voucher_id": str(voucher.id),
        "revision_id": str(revision.id),
        "header": visible("vouchers.voucher", snapshot.get("header", [])),
        "items": items,
    }
    # What an editor needs, resolved as a write would be: for the voucher's type at its current
    # revision (a write against an older revision is refused), on the revision's own dates. A type
    # that has since been retired, or revised so that the voucher's class belongs to a superseded
    # revision, still lets the saved capture be read, and says why it cannot be edited.
    try:
        evidence = await effective_configuration(
            company_id,
            voucher.type_id,
            revision.document_date,
            revision.class_id,
            revision.posting_date,
            current,
            db,
        )
    except (ConflictError, PermissionDeniedError, ValidationFailedError) as error:
        return pinned | {"configuration_unavailable": error.message}
    return pinned | await native_field_set(db, current, company_id, evidence)


@router.post("/vouchers", response_model=VoucherDetail, status_code=201)
async def create_voucher(
    company_id: uuid.UUID,
    body: VoucherInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await documents.write(db, current, body)
        await db.flush()
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await documents.detail(db, current, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "create",
            idempotency_key,
            body,
            mutate,
            render,
        )
    )


@router.put("/vouchers/{object_id}", response_model=VoucherDetail)
async def edit_voucher(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: VoucherEdit,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await documents.write(
            db,
            current,
            body.content,
            voucher_id=object_id,
            version=body.expected_version,
            assignment_override_reason=body.reason,
        )
        await db.flush()
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await documents.detail(db, current, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "edit",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


class ShareRequest(Contract):
    expected_version: int = Field(ge=1)
    party_id: uuid.UUID
    channel: Literal["email", "sms", "whatsapp"]


class ShareResult(Contract):
    voucher_id: uuid.UUID
    message_id: uuid.UUID
    status: Literal["queued"] = "queued"


@router.post("/vouchers/{object_id}/share", response_model=ShareResult, status_code=202)
async def share_voucher(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ShareRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        message_id = await notifications.share(
            db, current, object_id, body.expected_version, body.party_id, body.channel
        )
        return CommandReceipt(
            202,
            {
                "voucher_id": str(object_id),
                "message_id": str(message_id),
                "status": "queued",
            },
        )

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        await get(db, current, m.Voucher, object_id)
        return ShareResult.model_validate(refs).model_dump(mode="json")

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "share",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.post("/vouchers/{object_id}/issue", response_model=VoucherDetail)
async def issue_voucher(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: IssueRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    return await action_command(request, current, object_id, "issue", body, idempotency_key, body)


@router.post("/vouchers/{object_id}/{action}", response_model=VoucherDetail)
async def voucher_action(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    action: str,
    body: VoucherActionRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    if action in {"post", "reverse"}:
        authorize(current, action)
        raise ConflictError(
            "actual financial and stock execution is disabled until dependent batches are verified"
        )
    if action not in {"submit", "approve", "reject", "cancel", "accept", "decline", "expire"}:
        raise NotFoundError("voucher action not found")
    return await action_command(request, current, object_id, action, body, idempotency_key)


async def action_command(
    request: Request,
    current: Access,
    object_id: uuid.UUID,
    action: str,
    body: Version,
    key: str,
    issue: IssueRequest | None = None,
) -> JSONResponse:
    acknowledged = isinstance(body, VoucherActionRequest) and body.acknowledge_duplicate_bill

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await documents.action(
            db,
            current,
            object_id,
            action,
            body.expected_version,
            body.reason,
            issue,
            acknowledge_duplicate_bill=acknowledged,
        )
        await db.flush()
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await documents.detail(db, current, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            action,
            key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.get(
    "/vouchers/{object_id}/revisions/{revision_id}",
    response_model=VoucherDetail,
    response_model_exclude_unset=True,
)
async def voucher_revision(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    revision_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await documents.detail(db, current, object_id, revision_id)


@router.get("/{resource}", response_model=ResourcePage, response_model_exclude_unset=True)
async def list_resource(
    company_id: uuid.UUID,
    resource: str,
    query: Annotated[ListQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    model = RESOURCES.get(resource)
    if model is None:
        raise NotFoundError("resource not found")
    return await reads.listing(
        db,
        current,
        model,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/vouchers/{object_id}", response_model=VoucherDetail, response_model_exclude_unset=True
)
async def voucher_detail(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    return await documents.detail(db, current, object_id)


@router.get(
    "/{resource}/{object_id}", response_model=ResourceDetail, response_model_exclude_unset=True
)
async def resource_detail(
    company_id: uuid.UUID,
    resource: str,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    model = RESOURCES.get(resource)
    if model is None or model is m.Voucher:
        raise NotFoundError("resource not found")
    return await admin.detail(db, current, model, object_id)
