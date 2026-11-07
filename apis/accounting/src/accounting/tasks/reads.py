"""Lean, field-protected keyset reads and form metadata."""

from __future__ import annotations

from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import denied_fields
from billing_platform.idempotency import canonical_json
from billing_platform.listing import (
    FilterColumn,
    Page,
    SortColumn,
    apply_filters,
    apply_search,
    fetch_page,
    resolve_sort,
)
from billing_platform.pagination import CursorCodec
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.resources import BY_NAME, Resource
from accounting.schemas.metadata import resolved_schema
from accounting.schemas.query import FieldDescription, FieldSet, MasterQuery
from accounting.tasks.access import authority_fingerprint, authorize, permission, readable, rules
from accounting.tasks.commands import READ_ONLY
from accounting.tasks.party_role_queries import active_party_role

LIST_FIELDS = frozenset(
    {
        "id",
        "company_id",
        "row_version",
        "created_at",
        "updated_at",
        "code",
        "name",
        "label",
        "status",
        "kind",
        "party_id",
        "group_id",
        "head_id",
        "parent_id",
        "account_id",
        "role",
        "purpose",
        "scheme",
        "currency",
        "valid_from",
        "valid_to",
        "template_key",
        "template_version",
        "object_type",
        "system_key",
        "base_currency",
        "generation",
        "payment_term_id",
        "sequence",
        "account_number_last4",
        "commercial_type_id",
        "address_id",
        "contact_id",
    }
)


async def listing(
    db: AsyncSession,
    access: Access,
    spec: Resource,
    query: MasterQuery,
    secret: bytes,
    item_schema: type[BaseModel],
) -> Page[BaseModel]:
    authorize(access, spec, "read")
    allowed = readable(access, spec)
    fields = set(item_schema.model_fields) & allowed
    model: Any = spec.model
    role_columns = {}
    if spec.name == "party" and "roles" in item_schema.model_fields:
        if {"party_id", "role", "status"} <= readable(access, BY_NAME["party_role"]):
            role_columns = {
                role: active_party_role(access, model.id, role).label("_role_" + role)
                for role in ("CUSTOMER", "SUPPLIER", "OTHER", "BROKER")
            }
    statement = select(
        *(getattr(model, key).label(key) for key in sorted(fields)), *role_columns.values()
    ).where(model.company_id == access.context.company_id)
    filters = query.model_dump(exclude_none=True, exclude={"limit", "cursor", "q", "sort", "as_of"})
    if spec.name == "party" and query.role:
        statement = statement.where(active_party_role(access, model.id, query.role))
        filters.pop("role", None)
    if spec.name == "account" and query.role:
        # A party account's role: how a voucher takes the customer's receivable or the supplier's
        # payable without reading every account of a party that is both. A broker's is OTHER.
        if "party_role" not in allowed:
            raise PermissionDeniedError("account role is not readable")
        statement = statement.where(
            model.party_role == ("OTHER" if query.role == "BROKER" else query.role)
        )
        filters.pop("role", None)
    if query.as_of is not None:
        if spec.lifecycle != "dates":
            raise ValidationFailedError("as_of is only supported by effective-dated resources")
        if not {"valid_from", "valid_to"} <= allowed:
            raise PermissionDeniedError("effective dates are not readable")
        statement = statement.where(
            model.valid_from.is_(None) | (model.valid_from <= query.as_of),
            (model.valid_to.is_(None)) | (model.valid_to >= query.as_of),
        )
    if set(filters) - set(spec.detail.model_fields):
        raise ValidationFailedError("filter is not supported by this resource")
    statement = apply_filters(
        statement,
        filters,
        filters={key: FilterColumn(key, getattr(model, key)) for key in filters},
        readable=allowed,
    )
    searchable = tuple(key for key in ("code", "name", "label") if key in spec.detail.model_fields)
    if query.q and not searchable:
        raise ValidationFailedError("this resource has no text search")
    if query.q:
        statement = apply_search(
            statement,
            query.q,
            columns={key: getattr(model, key) for key in searchable},
            readable=allowed,
            minimum_length=2 if spec.name == "account" else 1,
        )
    sorts = {"id": SortColumn(model.id, "uuid")}
    supported = {("id",), ("-id",)}
    if "sort_order" in spec.detail.model_fields:
        sorts["sort_order"] = SortColumn(model.sort_order, "integer")
        supported |= {("sort_order",), ("-sort_order",)}
    if "name" in fields:
        sorts["name"] = SortColumn(model.name, "text")
        supported |= {("name",), ("-name",)}
    if spec.name == "account" and "code" in fields:
        sorts["code"] = SortColumn(model.code, "text")
        supported |= {("code",), ("-code",)}
    terms = resolve_sort(
        query.sort,
        default="code" if spec.name == "account" and "code" in fields else "id",
        columns=sorts,
        readable=allowed,
        supported=frozenset(supported),
    )
    context = canonical_json(
        {
            "resource": spec.name,
            "tenant": str(access.actor.tenant_id),
            "company": str(access.context.company_id),
            "authority": authority_fingerprint(access),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()

    def project(row: Any) -> BaseModel:
        values = dict(row)
        if role_columns:
            values["roles"] = [role for role in role_columns if values.pop("_role_" + role)]
        return item_schema.model_validate(values)

    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=project,
    )


def field_set(access: Access, spec: Resource) -> FieldSet:
    authorize(access, spec, "read")
    allowed = readable(access, spec)
    schema = resolved_schema(spec.create)
    required = set(schema.get("required", []))
    write_permissions = {permission(spec, "manage")}
    if spec.name == "fiscal_period":
        write_permissions.update({"period.close", "period.reopen", "period.lock"})
    can_write = spec.name not in READ_ONLY and any(
        access.actor.allows_scope(key, target=ScopePath(company_id=access.context.company_id))
        for key in write_permissions
    )
    denied = set(
        denied_fields(
            spec.create.model_fields,
            rules=rules(access, spec, None),
            access="write",
            target=ScopePath(company_id=access.context.company_id),
        )
    )
    input_read_denied = set(
        denied_fields(
            spec.create.model_fields,
            rules=rules(access, spec, None),
            access="read",
            target=ScopePath(company_id=access.context.company_id),
        )
    )
    layouts = {
        layout["field_key"]: layout
        for layout in access.context.layouts
        if layout.get("entity_type") == "accounting." + spec.name
    }
    result = []
    for key, definition in schema["properties"].items():
        layout = layouts.get(key, {})
        result.append(
            FieldDescription(
                key=key,
                label=layout.get("label_override") or key.replace("_", " ").capitalize(),
                required=(key in required or bool(layout.get("is_required")))
                and not (key == "code" and spec.name in {"account", "party"}),
                visible=layout.get("is_visible") is not False,
                readable=key in allowed
                if key in spec.detail.model_fields or spec.name in BY_NAME
                else key not in input_read_denied,
                writable=can_write and key not in denied,
                definition=definition,
                reference=(BY_NAME | FINANCIAL_BY_NAME)[spec.references[key]].path
                if key in spec.references
                else None,
            )
        )
    return FieldSet(resource=spec.path, fields=result)
