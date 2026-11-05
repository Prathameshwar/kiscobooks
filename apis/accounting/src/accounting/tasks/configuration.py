"""Editor hints only: native commands remain the authority for every mutation."""

import datetime as dt
from decimal import Decimal
from typing import Any, get_args

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.master_metadata import PRESENTATION
from accounting.resources import BY_PATH, Resource
from accounting.schemas.configuration import (
    ConfigurationField,
    ConfigurationForm,
    ConfigurationResource,
    Control,
    ControlKind,
    FormQuery,
)
from accounting.schemas.query import MasterQuery
from accounting.tasks.access import authorize, permission, readable
from accounting.tasks.commands import READ_ONLY, require_metadata
from accounting.tasks.company_configuration_controls import company_controls
from accounting.tasks.reads import field_set

EXTERNAL_REFERENCES = {
    "company_bank_id": "identity:bank-accounts",
    "company_registration_id": "identity:tax-registrations",
    "rule_id": "catalog:tax-rules",
    "supersedes_id": "withholding-rates",
}
REFERENCE_LABELS = {
    "party_id": "Party",
    "account_id": "Account",
    "offset_account_id": "Offset ledger account",
    "group_id": "Account group",
    "head_id": "Account head",
    "parent_id": "Parent group",
    "payment_term_id": "Payment term",
    "company_bank_id": "Company bank",
    "company_registration_id": "Company tax registration",
    "commercial_type_id": "Commercial type",
    "registration_id": "Tax registration",
    "address_id": "Address",
    "contact_id": "Contact",
    "rule_id": "Tax rule",
    "pan_identifier_id": "PAN business identifier",
    "default_section_id": "Default withholding section",
    "section_id": "Withholding section",
    "supersedes_id": "Replaces rate",
}


def configuration_spec(resource: ConfigurationResource) -> Resource:
    if resource == "charge-policies":
        from accounting.financial_resources import FINANCIAL_BY_NAME

        return FINANCIAL_BY_NAME["charge_policy"]
    return BY_PATH[resource]


def contains(annotation: Any, expected: type[Any]) -> bool:
    return annotation is expected or any(contains(arg, expected) for arg in get_args(annotation))


async def form(
    db: AsyncSession, current: Access, resource: ConfigurationResource, query: FormQuery
) -> ConfigurationForm:
    spec = configuration_spec(resource)
    authorize(current, spec, "read")
    await require_metadata(db, current)
    if query.operation == "update" and query.object_id is None:
        raise ValidationFailedError("editing requires an object identifier")
    if query.operation == "create" and query.object_id is not None:
        raise ValidationFailedError("creation cannot name an existing object")
    row: Any = (
        await company_object(db, spec.model, query.object_id, company_id=current.context.company_id)
        if query.object_id
        else None
    )
    native = field_set(current, spec)
    account: Any = None
    if query.operation == "update" and row is not None:
        protected = {key for key in ("system_key", "used_at") if key in spec.detail.model_fields}
        if spec.name == "account":
            protected.add("status")
        if spec.lifecycle == "dates":
            protected.update({"valid_from", "valid_to"})
        if spec.name in {"account_tax_profile", "account_bank_profile"}:
            protected.add("account_id")
            account_spec = BY_PATH["accounts"]
            authorize(current, account_spec, "read")
            if not {"status", "used_at"} <= readable(current, account_spec):
                raise PermissionDeniedError("account lifecycle required for editing is protected")
            account = await company_object(
                db, account_spec.model, row.account_id, company_id=current.context.company_id
            )
        if not protected <= readable(current, spec):
            raise PermissionDeniedError("lifecycle fields required for editing are protected")
    can_manage = spec.name not in READ_ONLY and current.actor.allows_scope(
        permission(spec, "manage"), target=ScopePath(company_id=current.context.company_id)
    )
    fields = []
    for field in native.fields:
        if field.label == field.key.replace("_", " ").capitalize():
            field = field.model_copy(update={"label": REFERENCE_LABELS.get(field.key, field.label)})
        definition = field.definition
        parts = definition.get("anyOf", [definition])
        meaningful = next((part for part in parts if part.get("type") != "null"), definition)
        typed = spec.create.model_fields[field.key]
        nullable = any(part.get("type") == "null" for part in parts)
        reference = field.reference or EXTERNAL_REFERENCES.get(field.key)
        if field.key.endswith("currency") or field.key == "currency":
            reference = "currencies"
        elif field.key == "country_code":
            reference = "countries"
        elif field.key == "state_code":
            reference = "states"
        kind: ControlKind = (
            "reference"
            if reference
            else "select"
            if meaningful.get("enum")
            else "decimal"
            if contains(typed.annotation, Decimal)
            else "date"
            if contains(typed.annotation, dt.date)
            else "datetime"
            if contains(typed.annotation, dt.datetime)
            else "boolean"
            if meaningful.get("type") == "boolean"
            else "integer"
            if meaningful.get("type") == "integer"
            else "text"
        )
        conditional = any(
            policy.get("entity_type") == "accounting." + spec.name
            and policy.get("field_key") == field.key
            and policy.get("condition") is not None
            for policy in current.context.policies
        )
        write_only = field.key not in spec.detail.model_fields
        editable = (
            can_manage
            and field.writable
            and field.visible
            and (field.readable or write_only)
            and not conditional
            and query.operation != "read"
        )
        if query.operation == "update":
            editable &= field.key in spec.update.model_fields and field.key not in spec.immutable
            if row is not None:
                if getattr(row, "system_key", None) or getattr(row, "used_at", None):
                    editable &= field.key in PRESENTATION
                if spec.name == "account" and row.status == "ACTIVE":
                    editable &= field.key in PRESENTATION
                if spec.name in {"account_tax_profile", "account_bank_profile"}:
                    editable &= account.status == "DRAFT" and account.used_at is None
                if spec.lifecycle == "dates" and (
                    row.valid_from is None or row.valid_from <= utcnow().date()
                ):
                    editable &= field.key == "valid_to" and (
                        row.valid_to is None or row.valid_to >= utcnow().date()
                    )
        choices = [str(value) for value in meaningful.get("enum", [])]
        if (
            query.operation == "update"
            and spec.name == "account"
            and field.key == "kind"
            and field.readable
            and not conditional
        ):
            choices = [value for value in choices if (value == "PARTY") == (row.kind == "PARTY")]
        fields.append(
            ConfigurationField(
                **field.model_dump(),
                editable=bool(editable),
                conditional_access=conditional,
                initial=definition.get("default"),
                control=Control(
                    kind=kind,
                    nullable=nullable,
                    choices=choices,
                    reference=reference,
                    write_only=write_only,
                    decimal_bounds=(
                        {
                            key: str(getattr(constraint, attribute))
                            for constraint in typed.metadata
                            for attribute, key in (
                                ("ge", "minimum"),
                                ("le", "maximum"),
                                ("gt", "exclusiveMinimum"),
                                ("lt", "exclusiveMaximum"),
                            )
                            if getattr(constraint, attribute, None) is not None
                        }
                        if kind == "decimal"
                        else None
                    ),
                ),
            )
        )
    unavailable_reason, notices = company_controls(
        current, spec.name, fields, authoring=query.operation != "read"
    )
    allowed = readable(current, spec)
    filter_keys = sorted(
        (set(MasterQuery.model_fields) - {"q", "sort", "cursor", "limit", "as_of"})
        & set(spec.detail.model_fields)
        & allowed
    )
    if spec.lifecycle == "dates" and {"valid_from", "valid_to"} <= allowed:
        filter_keys.append("as_of")
    if spec.name == "account":
        filter_keys.extend(key for key in ("currency", "currency_mode") if key in allowed)
    if spec.name == "party" and {"party_id", "role", "status"} <= readable(
        current, BY_PATH["party-roles"]
    ):
        filter_keys.append("role")
    searchable = {key for key in ("code", "name", "label") if key in spec.detail.model_fields}
    return ConfigurationForm(
        company_id=current.context.company_id,
        resource=resource,
        operation=query.operation,
        lifecycle=spec.lifecycle,
        can_create=can_manage and unavailable_reason is None,
        can_manage=can_manage and unavailable_reason is None,
        fields=fields,
        filter_keys=filter_keys,
        searchable=bool(searchable) and searchable <= allowed,
        unavailable_reason=unavailable_reason,
        notices=notices,
    )
