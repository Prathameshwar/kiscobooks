"""Project historical business evidence under current reader policy, without altering hashes."""

from typing import Any

from billing_platform.authz import Scope, ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.field_policy import FieldPolicyRule, denied_fields
from billing_platform.gateway import Actor

from audit.models import AuditEvent


def visible_changes(event: AuditEvent, current: Actor) -> dict[str, Any] | None:
    if not event.entity_type.startswith(("accounting.", "catalog.", "vouchers.")):
        return event.changes
    if current.field_policies is None or event.company_id is None:
        return {}
    target = ScopePath(company_id=event.company_id, department_id=event.department_id)
    # Legacy Catalog aggregate events mixed child field names into their parent changes.
    # Without historical child state, any applicable child deny withholds that aggregate.
    aggregate = event.entity_type in {
        "catalog.product_configuration_scope",
        "catalog.product_configuration_draft",
        "catalog.product_configuration_revision",
        "catalog.attribute_set_revision",
        "catalog.identifier_profile",
        "catalog.return_policy_revision",
        "catalog.bulk_job",
        "catalog.item_group",
        "vouchers.voucher",
    }
    aggregate_prefix = "vouchers." if event.entity_type.startswith("vouchers.") else "catalog."
    if aggregate and any(
        policy.entity_type.startswith(aggregate_prefix)
        and policy.effect == "deny"
        and target.includes(Scope(policy.scope_type, policy.scope_id))
        and (
            policy.subject_scope_type is None
            or target.includes(
                Scope(policy.subject_scope_type, policy.subject_scope_id or SCOPE_ALL)
            )
        )
        for policy in current.field_policies
    ):
        return {}
    rules = []
    for policy in current.field_policies:
        if policy.entity_type != event.entity_type:
            continue
        if policy.conditional and policy.effect == "allow":
            continue  # Current business state cannot establish historical allow conditions.
        if policy.subject_scope_type is not None and not target.includes(
            Scope(policy.subject_scope_type, policy.subject_scope_id or SCOPE_ALL)
        ):
            continue
        rules.append(
            FieldPolicyRule(
                policy.field_key, "read", policy.effect, Scope(policy.scope_type, policy.scope_id)
            )
        )
    fields = event.changes or {}
    policy_keys = {
        key: key.removeprefix("custom_field:") if event.entity_type.startswith("catalog.") else key
        for key in fields
    }
    denied = set(denied_fields(policy_keys.values(), rules=rules, access="read", target=target))
    return {key: value for key, value in fields.items() if policy_keys[key] not in denied}


def visible_context(event: AuditEvent) -> dict[str, Any] | None:
    """Business metadata is allowlisted independently of business-field permissions."""
    if not event.entity_type.startswith(("accounting.", "catalog.", "vouchers.")):
        return event.context
    if event.context is None:
        return None
    count = event.context.get("count")
    result: dict[str, Any] = {"count": count} if type(count) is int and 0 <= count <= 5000 else {}
    if event.entity_type == "catalog.bulk_job" and event.action == "catalog.bulk_job.export":
        format_value = event.context.get("format")
        if format_value in ("CSV", "XLSX"):
            result["format"] = format_value
    return result
