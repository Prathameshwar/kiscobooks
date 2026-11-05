"""Registered delivery purposes and constrained template data, without framework IO."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from billing_platform.errors import ValidationFailedError


@dataclass(frozen=True)
class UseCase:
    key: str
    owner: str
    source: str
    category: str
    triggers: tuple[str, ...]
    channels: tuple[str, ...]
    required_variables: tuple[str, ...] = ()


USE_CASES = (
    UseCase(
        "tenant.administrator.ready", "platform", "identity", "security",
        ("identity.tenant_administrator.ready",), ("email",),
        ("sign_in_url", "username"),
    ),
    UseCase(
        "user.invited",
        "platform",
        "identity",
        "security",
        ("identity.invitation.requested",),
        ("email",),
        ("invitation_url",),
    ),
    UseCase(
        "platform.staff.alert",
        "platform",
        "identity",
        "operational",
        ("identity.platform_notification.requested",),
        ("email", "sms", "whatsapp"),
        ("message",),
    ),
    *(
        UseCase(
            f"voucher.{action}",
            "tenant",
            "vouchers",
            "transactional",
            (f"vouchers.voucher.{trigger}",),
            ("email", "sms", "whatsapp"),
        )
        for action, trigger in (
            ("shared", "share"),
            ("issued", "issued"),
            ("accepted", "accepted"),
            ("posted", "posted"),
        )
    ),
)
# Source contract mirrored from Vouchers' code registry, not imported from its ORM.
VOUCHER_KINDS = (
    "contra",
    "payment",
    "receipt",
    "journal",
    "sales",
    "purchase",
    "credit_note",
    "debit_note",
    "receipt_note",
    "delivery_note",
    "rejections_in",
    "rejections_out",
    "stock_journal",
    "physical_stock",
    "material_in",
    "material_out",
    "purchase_order",
    "sales_order",
    "job_work_in_order",
    "job_work_out_order",
    "memorandum",
    "reversing_journal",
)
USE_CASES += tuple(
    UseCase(
        f"voucher.{kind}.{status}",
        "tenant",
        "vouchers",
        "transactional",
        ("vouchers.voucher.share", f"vouchers.voucher.{status}"),
        ("email", "sms", "whatsapp"),
        (
            "voucher_id",
            "voucher_kind",
            "voucher_number",
            "voucher_status",
            "document_date",
            "currency",
            "due_date",
            "party_id",
        ),
    )
    for kind in VOUCHER_KINDS
    for status in ("issued", "accepted", "posted")
)
PROVIDERS = {"ses": "email", "twilio": "sms", "meta": "whatsapp", "fcm": "push"}


def definition(key: str, *, owner: str | None = None) -> UseCase:
    for item in USE_CASES:
        if item.key == key and (owner is None or item.owner == owner):
            return item
    raise ValidationFailedError("unsupported notification use case for this owner")


def validate_schema(schema: dict[str, Any]) -> None:
    if not schema:  # Existing generic templates remain readable during migration.
        return
    allowed = {"type", "properties", "required", "additionalProperties"}
    if set(schema) - allowed or schema.get("type") != "object":
        raise ValidationFailedError("variable schema must be a supported object schema")
    props, required = schema.get("properties", {}), schema.get("required", [])
    if not isinstance(props, dict) or len(props) > 100 or not isinstance(required, list):
        raise ValidationFailedError("invalid variable schema")
    if any(
        not isinstance(k, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", k) for k in props
    ) or any(not isinstance(k, str) or k not in props for k in required):
        raise ValidationFailedError("schema required fields must name declared variables")
    for spec in props.values():
        if (
            not isinstance(spec, dict)
            or set(spec) - {"type", "maxLength", "enum"}
            or not isinstance(spec.get("type"), str)
            or spec.get("type") not in {"string", "integer", "boolean", "number"}
        ):
            raise ValidationFailedError("unsupported variable definition")
        if "maxLength" in spec and (
            type(spec["maxLength"]) is not int or not 1 <= spec["maxLength"] <= 10000
        ):
            raise ValidationFailedError("invalid variable length bound")
        if "enum" in spec and (
            not isinstance(spec["enum"], list) or not 1 <= len(spec["enum"]) <= 100
        ):
            raise ValidationFailedError("invalid variable enum")
    if schema.get("additionalProperties", False) is not False:
        raise ValidationFailedError("additional variables must be forbidden")


def validate_variables(schema: dict[str, Any], values: dict[str, Any]) -> None:
    validate_schema(schema)
    if not schema:
        return
    props = schema.get("properties", {})
    if set(values) - props.keys() or set(schema.get("required", [])) - values.keys():
        raise ValidationFailedError("template variables do not match the registered schema")
    for name, value in values.items():
        spec = props[name]
        expected = spec["type"]
        valid = (
            (expected == "string" and isinstance(value, str))
            or (expected == "integer" and type(value) is int)
            or (expected == "boolean" and type(value) is bool)
            or (expected == "number" and type(value) is int)
        )
        if not valid or (isinstance(value, str) and len(value) > spec.get("maxLength", 10000)):
            raise ValidationFailedError("invalid template variable", fields={name: "invalid value"})
        if "enum" in spec and value not in spec["enum"]:
            raise ValidationFailedError("template variable is outside its allowed values")


def validate_content(
    schema: dict[str, Any], texts: list[str | None], payload: dict[str, Any] | None
) -> None:
    validate_schema(schema)
    names = set().union(
        *(set(re.findall(r"{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}", t or "")) for t in texts)
    )
    if schema and names - schema.get("properties", {}).keys():
        raise ValidationFailedError("template references an undeclared variable")
    if payload is not None:
        if set(payload) - {"template_parameters", "components"}:
            raise ValidationFailedError("unsupported channel payload fields")
        params = payload.get("template_parameters", [])
        if (
            not isinstance(params, list)
            or len(params) > 100
            or any(not isinstance(p, str) or p not in schema.get("properties", {}) for p in params)
        ):
            raise ValidationFailedError("template parameters must name declared variables")
        components = payload.get("components", [])
        if not isinstance(components, list) or len(components) > 12:
            raise ValidationFailedError("invalid WhatsApp components")
        if components and params:
            raise ValidationFailedError("use components or legacy body parameters")
        identities: set[tuple[str, str]] = set()
        for component in components:
            if not isinstance(component, dict) or set(component) - {
                "type",
                "parameters",
                "sub_type",
                "index",
            }:
                raise ValidationFailedError("invalid WhatsApp component")
            kind = component.get("type")
            if kind not in ("header", "body", "button"):
                raise ValidationFailedError("unsupported WhatsApp component type")
            if kind == "button":
                if component.get("sub_type") != "url" or component.get("index") not in (
                    "0",
                    "1",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                ):
                    raise ValidationFailedError("only indexed URL buttons are supported")
            elif set(component) & {"sub_type", "index"}:
                raise ValidationFailedError("button fields require a button")
            identity = (kind, component.get("index", ""))
            if identity in identities:
                raise ValidationFailedError("duplicate WhatsApp component")
            identities.add(identity)
            parameters = component.get("parameters")
            if not isinstance(parameters, list) or not 1 <= len(parameters) <= (
                1 if kind in ("header", "button") else 100
            ):
                raise ValidationFailedError("invalid WhatsApp component parameters")
            for parameter in parameters:
                if (
                    not isinstance(parameter, dict)
                    or set(parameter) != {"type", "variable"}
                    or parameter["type"] != "text"
                    or not isinstance(parameter["variable"], str)
                    or parameter["variable"] not in schema.get("properties", {})
                ):
                    raise ValidationFailedError(
                        "WhatsApp text parameters must name declared variables"
                    )


def render_payload(payload: dict[str, Any] | None, variables: dict[str, Any]) -> dict[str, Any]:
    """Freeze the provider's ordered components at planning, before context retention."""
    if not payload:
        return {}
    components = [
        {
            **{key: value for key, value in component.items() if key != "parameters"},
            "parameters": [
                {"type": "text", "text": str(variables[p["variable"]])}
                for p in component["parameters"]
            ],
        }
        for component in payload.get("components", [])
    ]
    if payload.get("template_parameters"):
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(variables[name])}
                    for name in payload["template_parameters"]
                ],
            }
        ]
    return {"components": components}
