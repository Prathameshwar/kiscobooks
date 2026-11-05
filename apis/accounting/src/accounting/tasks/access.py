"""Native field policy, layout and resource permissions; shared resolvers do the mechanics."""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.authz import Scope, ScopePath
from billing_platform.custom_fields import condition_fields, condition_matches
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import FieldPolicyRule, assert_fields_writable, denied_fields
from billing_platform.idempotency import canonical_json
from pydantic import TypeAdapter, ValidationError
from pydantic_core import to_jsonable_python
from sqlalchemy import JSON

from accounting.api.auth import Access
from accounting.resources import Resource


def condition_value(value: Any) -> Any:
    # Keep Decimal as Decimal so equality and membership ignore the database's scale.
    return value if isinstance(value, Decimal) else to_jsonable_python(value)


def condition_values(spec: Resource, tree: dict[str, Any]) -> dict[str, Any]:
    """Normalize authored operands using the same types as native record fields."""
    if "op" in tree:
        return tree | {"rules": [condition_values(spec, child) for child in tree["rules"]]}
    if "value" not in tree or tree["cmp"] == "matches":
        return tree
    field = (spec.detail.model_fields | spec.create.model_fields)[tree["field"]]
    adapter: TypeAdapter[Any] = TypeAdapter(field.annotation)
    try:
        operand = tree["value"]
        values = operand if tree["cmp"] in {"in", "not_in"} else [operand]
        normalized = [condition_value(adapter.validate_python(value)) for value in values]
    except (ValidationError, TypeError, ValueError) as exc:
        raise PermissionDeniedError("field policy operand cannot be evaluated") from exc
    return tree | {"value": normalized if tree["cmp"] in {"in", "not_in"} else normalized[0]}


def permission(spec: Resource, action: str) -> str:
    if spec.name in {
        "stock_posting",
        "stock_movement",
        "stock_position",
        "stock_account_policy",
        "stock_cost_pool",
    }:
        return (
            "accounting.stock.read"
            if action == "read"
            else (
                "accounting.stock.configure"
                if spec.name == "stock_account_policy"
                else "accounting.stock.post"
            )
        )
    if spec.name in {"stock_lot", "stock_unit"}:
        family = "batch" if spec.name == "stock_lot" else "serial"
        return f"accounting.{family}.{action}"
    if spec.name.startswith("invoice_") or spec.name == "gst_return_record":
        return "ledger.read" if action == "read" else "ledger.post_journal"
    if spec.name in {
        "bank_instrument",
        "bank_instrument_event",
        "bank_statement_mapping",
        "bank_statement_import",
        "bank_statement_entry",
        "bank_match_event",
        "bank_reconciliation_session",
        "bank_opening_item",
        "bank_reconciliation_policy",
        "bank_adjustment_proposal",
    }:
        return "accounting.bank.read" if action == "read" else "accounting.bank.manage"
    if spec.name in {"charge_policy", "charge_assessment", "charge_tax_snapshot"}:
        return f"accounting.charges.{action}"
    if spec.name in {"credit_reservation", "credit_override"}:
        return "accounting.credit.read" if action == "read" else "accounting.credit.manage"
    if spec.name in {
        "journal",
        "journal_line",
        "journal_tax",
        "source_document",
        "open_item",
        "allocation",
    }:
        return "ledger.read" if action == "read" else "ledger.post_journal"
    if spec.name in {"financial_setup", "opening_batch"}:
        return f"accounting.finance.{action}"
    if spec.name in {"fiscal_year", "fiscal_period", "fiscal_transition"}:
        return f"period.{action}"
    family = "account"
    if spec.name in {"account_head"}:
        family = "head"
    elif spec.name in {"account_group", "account_group_closure", "account_group_alias"}:
        family = "group"
    elif spec.name in {
        "account_tax_profile",
        "account_tax_default",
        "party_tax_registration",
        "party_identifier",
        "party_registration_address",
    }:
        family = "tax"
    elif spec.name in {"account_bank_profile", "party_bank_account"}:
        family = "bank"
    elif spec.name == "account_posting_mapping":
        family = "mapping"
    elif spec.name in {
        "payment_term",
        "payment_term_line",
        "party_accounting_policy",
        "party_credit_policy",
    }:
        family = "policy"
    elif spec.name in {
        "accounting_setup",
        "account_template_installation",
        "account_template_binding",
    }:
        family = "setup"
    elif spec.name in {
        "withholding_section",
        "withholding_rate",
        "party_withholding_profile",
        "withholding_certificate",
    }:
        family = "withholding"
    elif spec.name.startswith("party"):
        family = "party"
    return f"accounting.{family}.{action}"


def authorize(access: Access, spec: Resource, action: str) -> None:
    access.context.assert_current(access.actor, access.context.company_id)
    access.actor.require_scope(
        permission(spec, action), target=ScopePath(company_id=access.context.company_id)
    )


def rules(access: Access, spec: Resource, values: dict[str, Any] | None) -> list[FieldPolicyRule]:
    result = []
    fields = frozenset(spec.create.model_fields) | frozenset(spec.detail.model_fields)
    for policy in access.context.policies:
        if policy.get("entity_type") != "accounting." + spec.name:
            continue
        shape = tuple(
            policy.get(key) for key in ("field_key", "access", "effect", "scope_type", "scope_id")
        )
        # Every check below is a membership or parse test, and both raise on a value of the wrong
        # type. Deny before that happens so a malformed policy cannot become a 500.
        if not all(isinstance(value, str) for value in shape):
            raise PermissionDeniedError("field policy cannot be evaluated")
        if (
            policy["field_key"] not in fields
            or policy["access"] not in {"read", "write"}
            or policy["effect"] not in {"allow", "deny"}
        ):
            raise PermissionDeniedError("field policy cannot be evaluated")
        condition = policy.get("condition")
        if condition is not None:
            try:
                condition_keys = condition_fields(condition, allowed=fields)
            except ValidationFailedError as exc:
                raise PermissionDeniedError("field policy cannot be evaluated") from exc
            if values is None or not condition_keys.issubset(values):
                if policy["effect"] == "allow":
                    continue
            elif not condition_matches(
                condition_values(spec, condition),
                {key: condition_value(value) for key, value in values.items()},
                numeric_fields=frozenset(
                    {"limit_amount", "overdue_tolerance", "percentage", "days", "overdue_days"}
                ),
            ):
                continue
        try:
            scope = Scope(policy["scope_type"], uuid.UUID(policy["scope_id"]))
        except ValueError as exc:
            raise PermissionDeniedError("field policy cannot be evaluated") from exc
        result.append(
            FieldPolicyRule(policy["field_key"], policy["access"], policy["effect"], scope)
        )
    return result


def readable(
    access: Access, spec: Resource, values: dict[str, Any] | None = None
) -> frozenset[str]:
    fields = frozenset(spec.detail.model_fields)
    denied = set(
        denied_fields(
            fields | frozenset(spec.create.model_fields),
            rules=rules(access, spec, values),
            access="read",
            target=ScopePath(company_id=access.context.company_id),
        )
    )
    if denied and spec.lifecycle == "command":
        # Financial JSON contains immutable copies of request/calculation fields. A deny on
        # any contributing field also hides those copies in details, replays and exports.
        denied.update(
            column.key for column in spec.model.__table__.columns if isinstance(column.type, JSON)
        )
    if spec.name == "invoice_supply_fact" and any(
        policy.get("access") == "read"
        and policy.get("effect") == "deny"
        and str(policy.get("entity_type", "")).startswith("accounting.")
        for policy in access.context.policies
    ):
        # The frozen proof contains copies of account/group/registration/default fields.
        # Mask it conservatively in detail, replay and export under contributing denies.
        denied.add("source_evidence")
    # Denying structural identity would make the resource unusable. Fail closed.
    if set(denied) & {"id", "company_id", "row_version", "created_at", "updated_at"}:
        raise PermissionDeniedError("resource identity is not readable")
    return fields - set(denied)


def writable(
    access: Access, spec: Resource, before: dict[str, Any], after: dict[str, Any]
) -> set[str]:
    changed = {key for key, value in after.items() if key not in before or before[key] != value}
    target = ScopePath(company_id=access.context.company_id)
    for values in (before, after) if before else (after,):
        assert_fields_writable(changed, rules=rules(access, spec, values), target=target)
    for layout in access.context.layouts:
        if (
            layout.get("entity_type") == "accounting." + spec.name
            and layout.get("is_required")
            and after.get(layout["field_key"]) in (None, "")
        ):
            raise ValidationFailedError("a configured required field is missing")
    return changed


def authority_fingerprint(access: Access) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "user": str(access.actor.user_id),
                "policies": list(access.context.policies),
                "permissions": sorted(access.actor.permissions),
            }
        )
    ).hexdigest()
