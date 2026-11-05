"""Restrictive, deterministic resolution shared by field sets and writes."""

import hashlib
from typing import Any, Literal

from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from voucher_execution.invoice import SALES_CONFIGURATION_FIELDS, restrict_invoice
from voucher_execution.money import restrict_money
from voucher_execution.stock import STOCK_PROFILES, StockPolicy

from vouchers.domain.purchase_calculation import preset_violation
from vouchers.domain.registry import FOUNDATION_SECTIONS, resolve_kind
from vouchers.domain.stock import restrict_stock
from vouchers.schemas.configuration import (
    CommercialAttributionConfiguration,
    CounterConfiguration,
    JobProcessConfiguration,
    ManufacturingConfiguration,
    MoneyConfiguration,
    NotificationConfiguration,
    OrderPolicy,
    Policy,
    SalesWorkflowConfiguration,
)


def restrict_commercial_attribution(
    parent: CommercialAttributionConfiguration, child: CommercialAttributionConfiguration
) -> CommercialAttributionConfiguration:
    def merge_mode(left: str, right: str) -> Literal["OFF", "OPTIONAL", "REQUIRED"]:
        modes = {left, right}
        if modes == {"OFF", "REQUIRED"}:
            raise ValidationFailedError("commercial attribution policies conflict")
        return "REQUIRED" if "REQUIRED" in modes else "OFF" if "OFF" in modes else "OPTIONAL"

    return CommercialAttributionConfiguration(
        seller=merge_mode(parent.seller, child.seller),
        broker=merge_mode(parent.broker, child.broker),
        collector=merge_mode(parent.collector, child.collector),
        return_handler=merge_mode(parent.return_handler, child.return_handler),
        payment_handler=merge_mode(parent.payment_handler, child.payment_handler),
        max_participants=min(parent.max_participants, child.max_participants),
        allow_line_assignments=parent.allow_line_assignments and child.allow_line_assignments,
    )


def restrict_counter(
    parent: CounterConfiguration, child: CounterConfiguration
) -> CounterConfiguration:
    modes = {parent.mode, child.mode}
    if modes == {"OFF", "REQUIRED"}:
        raise ValidationFailedError("counter policies conflict")
    return CounterConfiguration(
        mode="REQUIRED" if "REQUIRED" in modes else "OFF" if "OFF" in modes else "OPTIONAL",
        session_required=parent.session_required or child.session_required,
    )


def restrict_money_configuration(
    parent: MoneyConfiguration, child: MoneyConfiguration
) -> MoneyConfiguration:
    purposes = parent.allowed_purposes & child.allowed_purposes
    if not purposes:
        raise ValidationFailedError("contradictory inherited money purpose configuration")
    return MoneyConfiguration(
        allowed_purposes=purposes,
        allowed_tender_modes=parent.allowed_tender_modes & child.allowed_tender_modes,
        max_tenders=min(parent.max_tenders, child.max_tenders),
    )


def restrict_order(parent: OrderPolicy, child: OrderPolicy) -> OrderPolicy:
    values = child.model_dump()
    values["allowed_purposes"] = parent.allowed_purposes & child.allowed_purposes
    if not values["allowed_purposes"]:
        raise ValidationFailedError("contradictory inherited order purpose configuration")
    for key in ("max_validity_days", "max_required_by_days"):
        left, selected = getattr(parent, key), getattr(child, key)
        values[key] = (
            min(left, selected)
            if left is not None and selected is not None
            else left
            if left is not None
            else selected
        )
    for key in ("delivery_terms_required", "payment_terms_required"):
        values[key] = getattr(parent, key) or getattr(child, key)
    return OrderPolicy.model_validate(values)


def restrict_manufacturing(
    parent: ManufacturingConfiguration, child: ManufacturingConfiguration
) -> ManufacturingConfiguration:
    roles = parent.allowed_output_roles & child.allowed_output_roles
    if "PRIMARY" not in roles:
        raise ValidationFailedError("contradictory manufacturing output roles")
    return ManufacturingConfiguration(
        bom_required=parent.bom_required or child.bom_required,
        manual_variance_allowed=parent.manual_variance_allowed and child.manual_variance_allowed,
        partial_runs_allowed=parent.partial_runs_allowed and child.partial_runs_allowed,
        max_input_lines=min(parent.max_input_lines, child.max_input_lines),
        max_output_lines=min(parent.max_output_lines, child.max_output_lines),
        allowed_output_roles=roles,
    )


def restrict_job_process(
    parent: JobProcessConfiguration, child: JobProcessConfiguration
) -> JobProcessConfiguration:
    if parent.role is not None and child.role is not None and parent.role != child.role:
        raise ValidationFailedError("contradictory job-work directions")
    modes = parent.allowed_consumption_modes & child.allowed_consumption_modes
    if not modes:
        raise ValidationFailedError("contradictory job consumption choices")
    return JobProcessConfiguration(
        role=child.role or parent.role,
        order_required=parent.order_required or child.order_required,
        bom_required=parent.bom_required or child.bom_required,
        allowed_consumption_modes=modes,
    )


def restrict_sales_workflow(
    parent: SalesWorkflowConfiguration, child: SalesWorkflowConfiguration
) -> SalesWorkflowConfiguration:
    left, right = parent.max_due_days, child.max_due_days
    maximum = min(left, right) if left is not None and right is not None else left
    return SalesWorkflowConfiguration(
        max_due_days=maximum if maximum is not None else right,
        customer_order_reference_required=(
            parent.customer_order_reference_required or child.customer_order_reference_required
        ),
    )


def restrict_notification(
    parent: NotificationConfiguration, child: NotificationConfiguration
) -> NotificationConfiguration:
    return NotificationConfiguration(
        enabled=parent.enabled and child.enabled,
        manual_share_allowed=parent.manual_share_allowed and child.manual_share_allowed,
        channels=parent.channels & child.channels,
        automatic_events=parent.automatic_events & child.automatic_events,
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def policy_wire(policy: Policy) -> dict[str, object]:
    # V1 wires are intentionally complete: accepted hashes depend on that representation.
    # V2 stores only supplied keys so inherited defaults remain distinguishable from
    # explicit False, None and empty values when a policy is loaded again.
    values = policy.model_dump(mode="json", exclude_unset=policy.schema_version == 2)
    for key, value in values.items():
        if isinstance(value, list):
            values[key] = sorted(value)
    return values


def validate_sales_policy(policy: Policy) -> None:
    invoice = policy.invoice
    if invoice is None:
        return
    if (
        not invoice.sales_tax_profiles
        or invoice.sales_party_account_ids == frozenset()
        or invoice.sales_supply_account_ids == frozenset()
        or (invoice.manual_discounts_allowed and not invoice.sales_discount_scopes)
        or (
            invoice.charges_allowed
            and (not invoice.sales_charge_purposes or not invoice.sales_charge_scopes)
        )
        or (
            not invoice.sales_credit_allowed
            and not invoice.sales_tender_modes
            and not invoice.sales_advance_adjustments_allowed
        )
    ):
        raise ValidationFailedError("Sales configuration has no viable invoice choices")


def validate_policy(kind: str, profile: str, policy: Policy) -> None:
    spec = resolve_kind(kind, profile)
    if policy.purchase_calculation is not None:
        if (kind, profile) != ("PURCHASE", "STANDARD") or policy.invoice is None:
            raise ValidationFailedError("calculation presets require a standard Purchase invoice")
        for preset in policy.purchase_calculation.presets:
            if violation := preset_violation(preset, policy.invoice):
                raise ValidationFailedError(violation)
    if policy.manufacturing is not None:
        if (kind, profile) != ("STOCK_JOURNAL", "MANUFACTURING"):
            raise ValidationFailedError(
                "manufacturing controls require manufacturing Stock Journal"
            )
    if policy.job_process is not None:
        if kind not in {"JOB_WORK_IN_ORDER", "JOB_WORK_OUT_ORDER", "MATERIAL_IN", "MATERIAL_OUT"}:
            raise ValidationFailedError("job process controls require a job-work voucher")
        expected_role = {
            "JOB_WORK_OUT_ORDER": "PRINCIPAL",
            "JOB_WORK_IN_ORDER": "WORKER",
        }.get(kind)
        if policy.job_process.role is None or (
            expected_role is not None and policy.job_process.role != expected_role
        ):
            raise ValidationFailedError("job-work type requires its fixed principal/worker role")
    if policy.sales_workflow is not None and (kind, profile) != ("SALES", "STANDARD"):
        raise ValidationFailedError("Sales workflow controls require standard Sales vouchers")
    if policy.order is not None and not (
        kind in {"SALES_ORDER", "PURCHASE_ORDER"}
        or (kind == "STOCK_JOURNAL" and profile == "REQUISITION")
    ):
        raise ValidationFailedError("order controls require a non-posting order profile")
    if policy.order is not None and not policy.order.allowed_purposes:
        raise ValidationFailedError("order purpose choices cannot be empty")
    if policy.order is not None:
        expected_purposes = (
            {"PROCURE", "INTERNAL_ISSUE"}
            if kind == "STOCK_JOURNAL"
            else {"QUOTE"}
            if profile == "QUOTATION"
            else {"SALE"}
            if kind == "SALES_ORDER"
            else {"PURCHASE"}
        )
        if not any(purpose in policy.order.allowed_purposes for purpose in expected_purposes):
            raise ValidationFailedError("order configuration excludes this profile purpose")
    if policy.money is not None and kind not in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}:
        raise ValidationFailedError("money controls require an ordinary money voucher")
    if policy.money is not None and not policy.money.allowed_purposes:
        raise ValidationFailedError("money purpose choices cannot be empty")
    if policy.money is not None and (
        (kind == "CONTRA" and "TRANSFER" not in policy.money.allowed_purposes)
        or (profile == "ADVANCE" and "ADVANCE" not in policy.money.allowed_purposes)
        or (
            kind in {"PAYMENT", "RECEIPT"}
            and policy.money.allowed_purposes == frozenset({"BILL_ADJUSTMENT"})
        )
    ):
        raise ValidationFailedError("money configuration excludes this profile purpose")
    if kind == "SALES":
        validate_sales_policy(policy)
    if (
        policy.invoice is not None
        and policy.invoice.manual_discounts_allowed
        and (
            not policy.invoice.discount_input_kinds
            or not policy.invoice.discount_amount_bases
            or policy.invoice.max_discount_components == 0
            or policy.invoice.max_discount_pct == 0
            or policy.invoice.max_discount_amount == 0
        )
    ):
        raise ValidationFailedError("invoice configuration has no viable discount choices")
    if (
        kind != "SALES"
        and policy.invoice is not None
        and (SALES_CONFIGURATION_FIELDS & policy.invoice.model_dump(mode="json").keys())
    ):
        raise ValidationFailedError("Sales-only invoice controls require a Sales voucher type")
    if policy.invoice is not None and (
        kind not in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"}
        or (policy.schema_version == 2 and profile != "STANDARD")
    ):
        raise ValidationFailedError("invoice controls are unavailable for this kind")
    if policy.financial is not None and kind not in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}:
        raise ValidationFailedError("financial controls are unavailable for this kind")
    if policy.stock is not None and (kind, profile) not in STOCK_PROFILES.values():
        raise ValidationFailedError(
            "physical stock controls require a supported native stock profile"
        )
    available = FOUNDATION_SECTIONS | (
        {"ACCOUNTS", "TENDERS", "BILL_ALLOCATIONS"}
        if kind in {"JOURNAL", "CONTRA", "PAYMENT", "RECEIPT"}
        else set()
    )
    if kind in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"}:
        available |= {"ACCOUNTS", "CHARGES", "TAX", "TENDERS", "BILL_ALLOCATIONS"}
    if not policy.required_sections <= spec.sections & available:
        raise ValidationFailedError("required section is unavailable for this kind/profile")
    if "ITEMS" not in spec.sections and policy.default_mode != "ACCOUNTS":
        raise ValidationFailedError("this kind does not support item entry")
    if policy.required_sections & {"ITEMS"} and policy.max_lines == 0:
        raise ValidationFailedError("required items cannot have a zero line limit")
    if "PARTIES" in policy.required_sections and policy.max_parties == 0:
        raise ValidationFailedError("required parties cannot have a zero party limit")
    if "REFERENCES" in policy.forbidden_sections and (
        policy.supplier_reference_required
        or (
            policy.sales_workflow is not None
            and policy.sales_workflow.customer_order_reference_required
        )
    ):
        raise ValidationFailedError("required reference cannot be forbidden")


def explicit_approval_controls(policy: Policy) -> Policy:
    """A type that does not state an approval control keeps the schema default, not the envelope's.

    The company envelope starts permissive (no approval, self-approval allowed), and a sparse
    version 2 policy inherits whatever it leaves out. For a type, that would read a missing
    ``approval_required`` as "off" although the type form shows it as on, and now that submit can
    approve in one step the bill would skip a control the administrator sees as set. Writing the
    schema defaults into the type's own policy leaves classes and bindings below it inheriting
    from the type as before.
    """
    if policy.schema_version != 2 or {"approval_required", "self_approval_allowed"} <= (
        policy.model_fields_set
    ):
        return policy
    return Policy.model_validate(
        policy_wire(policy)
        | {
            "approval_required": policy.approval_required,
            "self_approval_allowed": policy.self_approval_allowed,
        }
    )


def intersect(parent: Policy, child: Policy) -> Policy:
    v2 = parent.schema_version == 2 or child.schema_version == 2
    value = policy_wire(child)

    def right(key: str) -> Any:
        if child.schema_version == 2 and key not in child.model_fields_set:
            return getattr(parent, key)
        return getattr(child, key)

    if v2:
        value["schema_version"] = 2
        for key in Policy.model_fields:
            if key not in value and key != "schema_version":
                value[key] = getattr(parent, key)
        for key in (
            "default_mode",
            "default_narration",
            "default_series_id",
            "default_template_revision_id",
        ):
            if key not in child.model_fields_set and child.schema_version == 2:
                value[key] = getattr(parent, key)
    child_invoice = child.invoice
    if (
        v2
        and child.schema_version == 2
        and parent.invoice is not None
        and child_invoice is not None
    ):
        child_invoice = type(child_invoice).model_validate(
            parent.invoice.model_dump()
            | {key: getattr(child_invoice, key) for key in child_invoice.model_fields_set}
        )
    invoice = (
        restrict_invoice(parent.invoice, child_invoice)
        if parent.invoice is not None and child_invoice is not None
        else parent.invoice or child_invoice
    )
    if invoice is not None:
        value["invoice"] = invoice.model_dump(mode="json")
        purchase = child.purchase_calculation or parent.purchase_calculation
        if purchase is not None:
            configured = purchase
            presets = tuple(
                preset for preset in configured.presets if preset_violation(preset, invoice) is None
            )
            value["purchase_calculation"] = {
                "presets": [preset.model_dump(mode="json") for preset in presets],
                "default_preset": configured.default_preset
                if any(preset.key == configured.default_preset for preset in presets)
                else None,
            }
    child_financial = child.financial
    if (
        v2
        and child.schema_version == 2
        and parent.financial is not None
        and child_financial is not None
    ):
        child_financial = type(child_financial).model_validate(
            parent.financial.model_dump()
            | {key: getattr(child_financial, key) for key in child_financial.model_fields_set}
        )
    financial = (
        restrict_money(parent.financial, child_financial)
        if parent.financial is not None and child_financial is not None
        else parent.financial or child_financial
    )
    if financial is not None:
        value["financial"] = financial.model_dump(mode="json")
    child_order = child.order
    if v2 and child.schema_version == 2 and parent.order is not None and child_order is not None:
        child_order = OrderPolicy.model_validate(
            parent.order.model_dump()
            | {key: getattr(child_order, key) for key in child_order.model_fields_set}
        )
    order = (
        restrict_order(parent.order, child_order)
        if parent.order is not None and child_order is not None
        else parent.order or child_order
    )
    if order is not None:
        value["order"] = order.model_dump(mode="json")
    child_money = child.money
    if v2 and child.schema_version == 2 and parent.money is not None and child_money is not None:
        child_money = MoneyConfiguration.model_validate(
            parent.money.model_dump()
            | {key: getattr(child_money, key) for key in child_money.model_fields_set}
        )
    money = (
        restrict_money_configuration(parent.money, child_money)
        if parent.money is not None and child_money is not None
        else parent.money or child_money
    )
    if money is not None:
        value["money"] = money.model_dump(mode="json")
    for key, contract, restrict in (
        ("stock", StockPolicy, restrict_stock),
        ("manufacturing", ManufacturingConfiguration, restrict_manufacturing),
        ("job_process", JobProcessConfiguration, restrict_job_process),
        ("sales_workflow", SalesWorkflowConfiguration, restrict_sales_workflow),
        (
            "commercial_attribution",
            CommercialAttributionConfiguration,
            restrict_commercial_attribution,
        ),
        ("counter", CounterConfiguration, restrict_counter),
        ("notification", NotificationConfiguration, restrict_notification),
    ):
        left, selected = getattr(parent, key), getattr(child, key)
        if v2 and child.schema_version == 2 and left is not None and selected is not None:
            selected = contract.model_validate(
                left.model_dump()
                | {field: getattr(selected, field) for field in selected.model_fields_set}
            )
        merged = (
            restrict(left, selected)
            if left is not None and selected is not None
            else left or selected
        )
        if merged is not None:
            value[key] = merged.model_dump(mode="json")
    for key in ("allowed_modes", "allowed_party_roles"):
        value[key] = sorted(getattr(parent, key) & right(key))
    for key in (
        "required_sections",
        "forbidden_sections",
        "required_header_fields",
        "required_item_fields",
    ):
        value[key] = sorted(getattr(parent, key) | right(key))
    for key in ("max_lines", "max_parties", "backdate_days", "future_days"):
        value[key] = min(getattr(parent, key), right(key))
    for key in (
        "narration_required",
        "line_description_required",
        "approval_required",
        "supplier_reference_required",
    ):
        value[key] = getattr(parent, key) or right(key)
    value["self_approval_allowed"] = parent.self_approval_allowed and right("self_approval_allowed")
    for key in (
        "header_field_keys",
        "item_field_keys",
        "allowed_series_ids",
        "allowed_template_revision_ids",
    ):
        left, selected = getattr(parent, key), right(key)
        value[key] = (
            sorted(
                left & selected
                if left is not None and selected is not None
                else left
                if left is not None
                else selected
            )
            if left is not None or selected is not None
            else None
        )
    for key in ("default_series_id", "default_template_revision_id"):
        if v2 and child.schema_version == 2:
            value[key] = (
                getattr(child, key) if key in child.model_fields_set else getattr(parent, key)
            )
        else:
            value[key] = getattr(child, key) or getattr(parent, key)
    try:
        return Policy.model_validate(value)
    except ValueError as exc:
        raise ValidationFailedError("contradictory inherited voucher configuration") from exc
