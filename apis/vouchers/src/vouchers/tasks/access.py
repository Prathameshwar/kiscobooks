"""Field denies are checked on changed values and every read, including replays."""

import uuid
from typing import Any

from billing_platform.authz import Scope, ScopePath
from billing_platform.custom_fields import condition_fields, condition_matches
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import FieldPolicyRule, denied_fields

from vouchers.api.auth import Access
from vouchers.domain.configuration import digest


def authorize(current: Access, action: str) -> None:
    current.context.assert_current(current.actor, current.context.company_id)
    current.actor.require_scope(
        "vouchers." + action, target=ScopePath(company_id=current.context.company_id)
    )


def policy_rules(
    current: Access, entity: str, values: dict[str, Any] | None
) -> list[FieldPolicyRule]:
    result = []
    for policy in current.context.policies:
        if policy.get("entity_type") != entity:
            continue
        try:
            key = policy["field_key"]
            if isinstance(key, str):
                key = key.removeprefix("custom_field:")
            access, effect = policy["access"], policy["effect"]
            if (
                not isinstance(key, str)
                or access not in {"read", "write"}
                or effect not in {"allow", "deny"}
            ):
                raise ValueError("invalid policy")
            condition = policy.get("condition")
            if condition is not None:
                fields = condition_fields(
                    condition, allowed=frozenset((values or {}).keys()) | {key}
                )
                if values is None or not fields <= values.keys():
                    if effect == "allow":
                        continue
                elif not condition_matches(condition, values):
                    continue
            result.append(
                FieldPolicyRule(
                    key, access, effect, Scope(policy["scope_type"], uuid.UUID(policy["scope_id"]))
                )
            )
        except (KeyError, TypeError, ValueError, ValidationFailedError) as exc:
            raise PermissionDeniedError("field policy cannot be evaluated") from exc
    return result


def denied(
    current: Access, entity: str, fields: set[str], mode: str, values: dict[str, Any] | None = None
) -> set[str]:
    return set(
        denied_fields(
            fields,
            rules=policy_rules(current, entity, values),
            access=mode,
            target=ScopePath(company_id=current.context.company_id),
        )
    )


def writable(current: Access, entity: str, before: dict[str, Any], after: dict[str, Any]) -> None:
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    # A conditional deny applying either before or after a change cannot be bypassed by the change.
    if denied(current, entity, changed, "write", before) | denied(
        current, entity, changed, "write", after
    ):
        raise PermissionDeniedError("changed voucher fields are not writable")


def fingerprint(current: Access) -> str:
    return digest(
        {
            "tenant": str(current.actor.tenant_id),
            "company": str(current.context.company_id),
            "user": str(current.actor.user_id),
            "policies": list(current.context.policies),
        }
    )


def mask(current: Access, entity: str, values: dict[str, Any]) -> dict[str, Any]:
    flat = values | values.get("custom_fields", {})
    blocked = denied(current, entity, set(flat), "read", flat)
    if blocked & {"id", "company_id", "row_version", "revision_id", "type_revision_id"}:
        raise PermissionDeniedError("voucher identity is not readable")
    result = {key: value for key, value in values.items() if key not in blocked}
    if "custom_fields" in result:
        result["custom_fields"] = {
            key: value for key, value in result["custom_fields"].items() if key not in blocked
        }
    return result


def visible_custom_keys(
    current: Access, entity: str, definitions: list[dict[str, Any]]
) -> set[str]:
    """Hide field metadata whose condition depends on unreadable or unbound fields."""
    native = (
        {"document_date", "currency", "mode", "narration"}
        if entity == "vouchers.voucher"
        else {"actual_quantity", "billed_quantity", "item_id", "unit_id"}
    )
    keys = {definition["key"] for definition in definitions}
    allowed = frozenset(native | keys)
    blocked = denied(current, entity, set(allowed) | {"custom_fields"}, "read")
    if "custom_fields" in blocked:
        return set()
    visible = keys - blocked
    native_visible = native - blocked
    while True:
        before = visible.copy()
        for definition in definitions:
            key = definition["key"]
            if key not in visible:
                continue
            references = (
                {definition["depends_on_key"]} if definition.get("depends_on_key") else set()
            )
            try:
                if definition.get("visibility") is not None:
                    references |= condition_fields(definition["visibility"], allowed=allowed)
            except ValidationFailedError:
                visible.remove(key)
                continue
            if not references <= visible | native_visible:
                visible.remove(key)
        if visible == before:
            return visible
