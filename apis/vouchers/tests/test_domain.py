import datetime as dt
import uuid

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError

from vouchers.domain.configuration import intersect, policy_wire, validate_policy
from vouchers.domain.documents import transition, validate_content
from vouchers.schemas.configuration import OrderPolicy, Policy, SalesWorkflowConfiguration
from vouchers.schemas.documents import VoucherInput

DAY = dt.date(2026, 4, 1)
BASE = {"type_revision_id": uuid.uuid4(), "document_date": DAY, "currency": "INR"}
ITEM = {
    "line_key": uuid.uuid4(),
    "item": {
        "item_id": uuid.uuid4(),
        "item_version": 1,
        "unit_id": uuid.uuid4(),
        "actual_quantity": "1",
        "billed_quantity": "1",
    },
}


@pytest.mark.parametrize(
    "policy,content,stage",
    [
        ({"allowed_modes": ["ACCOUNTS"]}, {"mode": "ITEMS"}, "DRAFT"),
        (
            {"forbidden_sections": ["REFERENCES"]},
            {"references": [{"purpose": "EXTERNAL", "reference": "x"}]},
            "DRAFT",
        ),
        ({}, {"lines": [ITEM]}, "DRAFT"),
        ({"max_lines": 0}, {"mode": "ITEMS", "lines": [ITEM]}, "DRAFT"),
        (
            {"allowed_party_roles": ["CUSTOMER"]},
            {"parties": [{"role": "SUPPLIER", "party_id": uuid.uuid4(), "source_version": 1}]},
            "DRAFT",
        ),
        ({"future_days": 0}, {"document_date": DAY + dt.timedelta(days=1)}, "DRAFT"),
        ({"header_field_keys": []}, {"custom_fields": {"cf_unbound": "x"}}, "DRAFT"),
        ({"required_sections": ["REFERENCES"]}, {}, "SUBMITTED"),
        ({"narration_required": True}, {}, "SUBMITTED"),
        ({"line_description_required": True}, {"mode": "ITEMS", "lines": [ITEM]}, "SUBMITTED"),
        ({"supplier_reference_required": True}, {}, "SUBMITTED"),
        ({"required_header_fields": ["cf_missing"]}, {}, "SUBMITTED"),
    ],
)
def test_configured_capture_is_enforced(policy, content, stage):
    with pytest.raises(ValidationFailedError):
        validate_content(
            VoucherInput.model_validate(BASE | content),
            Policy.model_validate(policy),
            kind="MEMORANDUM",
            profile="STANDARD",
            stage=stage,
            today=DAY,
        )


def test_kind_sections_and_invalid_configurations():
    with pytest.raises(ValidationFailedError):
        validate_content(
            VoucherInput.model_validate(BASE | {"mode": "ITEMS", "lines": [ITEM]}),
            Policy(),
            kind="JOURNAL",
            profile="STANDARD",
            stage="DRAFT",
            today=DAY,
        )
    for kind, policy in [
        ("JOURNAL", Policy(required_sections={"ITEMS"})),
        ("JOURNAL", Policy(default_mode="ITEMS")),
        ("SALES", Policy(required_sections={"ITEMS"}, max_lines=0)),
    ]:
        with pytest.raises(ValidationFailedError):
            validate_policy(kind, "STANDARD", policy)
    with pytest.raises(ValidationFailedError):
        validate_policy("SALES", "UNKNOWN", Policy())
    with pytest.raises(ValidationFailedError):
        intersect(
            Policy(required_sections={"REFERENCES"}), Policy(forbidden_sections={"REFERENCES"})
        )


def test_order_uses_planned_units_without_claiming_physical_or_billed_units():
    line = ITEM | {
        "item": ITEM["item"]
        | {"actual_quantity": "0", "billed_quantity": "0", "planned_quantity": "10"}
    }
    valid = VoucherInput.model_validate(
        BASE
        | {
            "mode": "ITEMS",
            "lines": [line],
            "parties": [{"role": "CUSTOMER", "party_id": uuid.uuid4(), "source_version": 1}],
            "fulfillment_terms": {"purpose": "QUOTE", "valid_until": "2026-04-30"},
        }
    )
    validate_content(
        valid, Policy(), kind="SALES_ORDER", profile="QUOTATION", stage="SUBMITTED", today=DAY
    )
    with pytest.raises(ValidationFailedError, match="expired"):
        validate_content(
            valid,
            Policy(),
            kind="SALES_ORDER",
            profile="QUOTATION",
            stage="SUBMITTED",
            today=dt.date(2026, 5, 1),
        )
    for change in (
        {"lines": [ITEM]},
        {"fulfillment_terms": {"purpose": "SALE"}},
        {"fulfillment_terms": {"purpose": "QUOTE", "valid_until": "2026-03-31"}},
        {"posting_date": DAY},
        {"parties": []},
    ):
        with pytest.raises(ValidationFailedError):
            validate_content(
                VoucherInput.model_validate(valid.model_dump() | change),
                Policy(),
                kind="SALES_ORDER",
                profile="QUOTATION",
                stage="SUBMITTED",
                today=DAY,
            )
    with pytest.raises(ValidationFailedError):
        validate_content(
            valid, Policy(), kind="SALES", profile="STANDARD", stage="DRAFT", today=DAY
        )
    legacy = VoucherInput.model_validate(BASE | {"mode": "ITEMS", "lines": [ITEM]})
    assert "planned_quantity" not in legacy.model_dump(mode="json")["lines"][0]["item"]


@pytest.mark.parametrize(
    "state,action",
    [
        ("ISSUED", "cancel"),
        ("DRAFT", "approve"),
        ("APPROVED", "submit"),
        ("CANCELLED", "issue"),
        ("DRAFT", "unknown"),
    ],
)
def test_invalid_transitions_do_not_change_evidence(state, action):
    with pytest.raises(ConflictError):
        transition(state, action, approval_required=True)


@pytest.mark.parametrize(
    "action,target",
    [("accept", "ACCEPTED"), ("decline", "DECLINED"), ("expire", "EXPIRED")],
)
def test_issued_nonposting_order_decisions_are_profile_gated(action, target):
    assert transition("ISSUED", action, approval_required=True, nonposting_order=True) == target
    with pytest.raises(ConflictError):
        transition("ISSUED", action, approval_required=True)
    with pytest.raises(ConflictError):
        transition(target, action, approval_required=True, nonposting_order=True)


def test_policy_resource_defaults_are_restrictive_and_deterministic():
    from vouchers.domain.configuration import policy_wire

    first, second = uuid.uuid4(), uuid.uuid4()
    parent = Policy(allowed_series_ids=frozenset({first}), default_series_id=first)
    effective = intersect(parent, Policy())
    assert effective.default_series_id == first
    assert policy_wire(effective)["allowed_series_ids"] == [str(first)]
    with pytest.raises(ValidationFailedError):
        intersect(parent, Policy(default_series_id=second))
    with pytest.raises(ValueError):
        Policy(allowed_template_revision_ids=frozenset(), default_template_revision_id=first)


def test_v2_policy_roundtrip_preserves_omitted_defaults_and_explicit_restrictions():
    from voucher_execution.money import MoneyPolicy

    from vouchers.domain.configuration import digest, policy_wire

    legacy = policy_wire(Policy())
    assert legacy["schema_version"] == 1 and "default_mode" in legacy
    parent = Policy(
        schema_version=2,
        default_narration="Inherited narration",
        financial=MoneyPolicy(
            split_tenders_allowed=True,
            allocations_allowed=True,
            settlement_adjustments_allowed=True,
        ),
    )
    child = Policy(schema_version=2, financial=MoneyPolicy(allocations_allowed=False))
    wire = policy_wire(child)
    assert wire["schema_version"] == 2
    assert "default_narration" not in wire
    assert wire["financial"] == {"allocations_allowed": False}
    loaded = Policy.model_validate(wire)
    merged = intersect(parent, loaded)
    assert merged.default_narration == "Inherited narration"
    assert merged.financial is not None
    assert merged.financial.split_tenders_allowed
    assert not merged.financial.allocations_allowed
    assert merged.financial.settlement_adjustments_allowed
    assert digest(policy_wire(Policy.model_validate(legacy))) == digest(legacy)


def test_v2_sparse_sales_policy_inherits_restrictions_and_rejects_pro_forma():
    from voucher_execution.invoice import InvoicePolicy

    from vouchers.domain.configuration import policy_wire

    parent = Policy(schema_version=2, invoice=InvoicePolicy(sales_credit_allowed=False))
    child = Policy.model_validate({"schema_version": 2, "invoice": {}})
    merged = intersect(parent, Policy.model_validate(policy_wire(child)))
    assert merged.invoice is not None and not merged.invoice.sales_credit_allowed
    validate_policy("SALES", "STANDARD", merged)
    with pytest.raises(ValidationFailedError, match="invoice controls are unavailable"):
        validate_policy("SALES", "PRO_FORMA", child)


def test_v2_manufacturing_and_job_controls_are_restrictive_and_fail_closed():
    from vouchers.domain.configuration import policy_wire
    from vouchers.schemas.configuration import JobProcessConfiguration, ManufacturingConfiguration

    assert "manufacturing" not in policy_wire(Policy())
    assert "job_process" not in policy_wire(Policy())
    parent = Policy(
        schema_version=2,
        manufacturing=ManufacturingConfiguration(
            manual_variance_allowed=True,
            max_output_lines=3,
            allowed_output_roles=frozenset({"PRIMARY", "BY_PRODUCT"}),
        ),
    )
    child = Policy.model_validate(
        {"schema_version": 2, "manufacturing": {"max_input_lines": 5}}
    )
    assert policy_wire(child)["manufacturing"] == {"max_input_lines": 5}
    merged = intersect(parent, Policy.model_validate(policy_wire(child)))
    assert merged.manufacturing is not None
    assert merged.manufacturing.max_input_lines == 5
    assert merged.manufacturing.max_output_lines == 3
    assert merged.manufacturing.manual_variance_allowed
    validate_policy("STOCK_JOURNAL", "MANUFACTURING", merged)
    with pytest.raises(ValidationFailedError, match="manufacturing Stock Journal"):
        validate_policy("STOCK_JOURNAL", "TRANSFER", merged)
    with pytest.raises(ValueError, match="published BOM"):
        ManufacturingConfiguration(bom_required=False)

    principal = Policy(
        schema_version=2,
        job_process=JobProcessConfiguration(role="PRINCIPAL", order_required=True),
    )
    narrowed = intersect(
        principal,
        Policy.model_validate({"schema_version": 2, "job_process": {"bom_required": True}}),
    )
    assert narrowed.job_process is not None
    assert narrowed.job_process.role == "PRINCIPAL"
    assert narrowed.job_process.order_required and narrowed.job_process.bom_required
    validate_policy("JOB_WORK_OUT_ORDER", "STANDARD", narrowed)
    with pytest.raises(ValidationFailedError, match="fixed principal/worker role"):
        validate_policy("JOB_WORK_IN_ORDER", "STANDARD", narrowed)
    with pytest.raises(ValidationFailedError, match="contradictory job-work directions"):
        intersect(
            principal,
            Policy(schema_version=2, job_process=JobProcessConfiguration(role="WORKER")),
        )
    with pytest.raises(ValueError, match="atomic stock owner"):
        JobProcessConfiguration(allowed_consumption_modes=frozenset({"COMBINED"}))


def test_v2_explicit_mode_and_narration_survive_sparse_inheritance():
    series_id = uuid.uuid4()
    parent = Policy(
        schema_version=2,
        default_mode="ITEMS",
        default_narration="Original",
        approval_required=False,
        self_approval_allowed=True,
        allowed_series_ids=frozenset({series_id}),
        default_series_id=series_id,
    )
    inherited = intersect(parent, Policy.model_validate({"schema_version": 2}))
    assert inherited.default_mode == "ITEMS" and inherited.default_narration == "Original"
    assert not inherited.approval_required and inherited.self_approval_allowed
    changed = intersect(
        parent, Policy.model_validate({"schema_version": 2, "default_narration": ""})
    )
    assert changed.default_narration == ""
    assert (
        intersect(parent, Policy(schema_version=2, default_series_id=None)).default_series_id
        is None
    )
    assert intersect(parent, Policy(schema_version=2, approval_required=True)).approval_required
    assert not intersect(
        parent, Policy(schema_version=2, self_approval_allowed=False)
    ).self_approval_allowed


def test_v2_order_terms_are_restrictive_and_profile_scoped():
    with pytest.raises(ValueError, match="schema v2"):
        Policy(order=OrderPolicy())
    with pytest.raises(ValidationFailedError, match="non-posting order"):
        validate_policy("JOURNAL", "STANDARD", Policy(schema_version=2, order=OrderPolicy()))
    policy = Policy(
        schema_version=2,
        order=OrderPolicy(
            allowed_purposes=frozenset({"QUOTE"}),
            max_validity_days=10,
            delivery_terms_required=True,
        ),
    )
    validate_policy("SALES_ORDER", "QUOTATION", policy)
    parent = Policy(schema_version=2, order=OrderPolicy(max_validity_days=5))
    merged = intersect(
        parent,
        Policy.model_validate({"schema_version": 2, "order": {"payment_terms_required": True}}),
    )
    assert merged.order is not None
    assert merged.order.max_validity_days == 5 and merged.order.payment_terms_required
    with pytest.raises(ValidationFailedError, match="contradictory inherited order"):
        intersect(
            Policy(schema_version=2, order=OrderPolicy(allowed_purposes=frozenset({"QUOTE"}))),
            Policy(schema_version=2, order=OrderPolicy(allowed_purposes=frozenset({"PURCHASE"}))),
        )
    item = ITEM | {
        "item": ITEM["item"]
        | {"actual_quantity": "0", "billed_quantity": "0", "planned_quantity": "1"}
    }
    body = VoucherInput.model_validate(
        BASE
        | {
            "mode": "ITEMS",
            "lines": [item],
            "parties": [{"role": "CUSTOMER", "party_id": uuid.uuid4(), "source_version": 1}],
            "fulfillment_terms": {"purpose": "QUOTE", "valid_until": "2026-04-08"},
        }
    )
    with pytest.raises(ValidationFailedError, match="terms are missing"):
        validate_content(
            body, policy, kind="SALES_ORDER", profile="QUOTATION", stage="SUBMITTED", today=DAY
        )
    assert body.fulfillment_terms is not None
    changed = body.model_copy(
        update={
            "fulfillment_terms": body.fulfillment_terms.model_copy(
                update={"valid_until": dt.date(2026, 4, 15)}
            )
        }
    )
    with pytest.raises(ValidationFailedError, match="validity exceeds"):
        validate_content(
            changed,
            policy,
            kind="SALES_ORDER",
            profile="QUOTATION",
            stage="SUBMITTED",
            today=DAY,
        )


def test_sales_workflow_sparse_policy_merges_restrictively_without_v1_wire_change():
    assert "sales_workflow" not in policy_wire(Policy())
    parent = Policy(
        schema_version=2,
        sales_workflow=SalesWorkflowConfiguration(max_due_days=60),
    )
    child = Policy.model_validate({
        "schema_version": 2,
        "sales_workflow": {"customer_order_reference_required": True},
    })
    merged = intersect(parent, Policy.model_validate(policy_wire(child)))
    assert merged.sales_workflow is not None
    assert merged.sales_workflow.max_due_days == 60
    assert merged.sales_workflow.customer_order_reference_required
    narrowed = intersect(
        merged, Policy(schema_version=2, sales_workflow=SalesWorkflowConfiguration(max_due_days=30))
    )
    assert narrowed.sales_workflow is not None
    assert narrowed.sales_workflow.max_due_days == 30
    assert narrowed.sales_workflow.customer_order_reference_required


def test_explicit_null_cannot_clear_parent_zero_day_order_limits():
    parent = Policy(
        schema_version=2,
        order=OrderPolicy(max_validity_days=0, max_required_by_days=0),
    )
    child = Policy.model_validate({
        "schema_version": 2,
        "order": {"max_validity_days": None, "max_required_by_days": None},
    })
    merged = intersect(parent, Policy.model_validate(policy_wire(child)))
    assert merged.order is not None
    assert merged.order.max_validity_days == 0
    assert merged.order.max_required_by_days == 0


def test_required_supplier_invoice_reference_must_be_nonblank():
    body = VoucherInput.model_validate(
        BASE | {"references": [{"purpose": "SUPPLIER_INVOICE", "reference": "  "}]}
    )
    with pytest.raises(ValidationFailedError, match="supplier reference"):
        validate_content(
            body,
            Policy(supplier_reference_required=True),
            kind="PURCHASE",
            profile="STANDARD",
            stage="ISSUED",
            today=DAY,
        )


@pytest.mark.parametrize(
    "kind,profile,purposes",
    [
        ("SALES_ORDER", "QUOTATION", frozenset({"SALE"})),
        ("PURCHASE_ORDER", "STANDARD", frozenset({"QUOTE"})),
        ("STOCK_JOURNAL", "REQUISITION", frozenset({"SALE"})),
    ],
)
def test_order_policy_must_allow_the_kind_purpose(kind, profile, purposes):
    with pytest.raises(ValidationFailedError, match="purpose"):
        validate_policy(
            kind, profile,
            Policy(schema_version=2, order=OrderPolicy(allowed_purposes=purposes)),
        )


@pytest.mark.parametrize("kind,profile,purpose", [
    ("CONTRA", "STANDARD", "GENERAL"),
    ("PAYMENT", "ADVANCE", "GENERAL"),
    ("RECEIPT", "ADVANCE", "REFUND"),
    ("PAYMENT", "STANDARD", "BILL_ADJUSTMENT"),
])
def test_money_policy_must_allow_the_profile_purpose(kind, profile, purpose):
    from vouchers.schemas.configuration import MoneyConfiguration

    with pytest.raises(ValidationFailedError, match="purpose"):
        validate_policy(
            kind, profile,
            Policy(
                schema_version=2,
                money=MoneyConfiguration(allowed_purposes=frozenset({purpose})),
            ),
        )


@pytest.mark.parametrize(
    "kind,policy",
    [
        ("PURCHASE", Policy(required_sections=frozenset({"PARTIES"}), max_parties=0)),
        (
            "PURCHASE",
            Policy(supplier_reference_required=True, forbidden_sections=frozenset({"REFERENCES"})),
        ),
        (
            "SALES",
            Policy(
                schema_version=2,
                forbidden_sections=frozenset({"REFERENCES"}),
                sales_workflow=SalesWorkflowConfiguration(customer_order_reference_required=True),
            ),
        ),
    ],
)
def test_policy_rejects_required_evidence_that_it_forbids(kind, policy):
    with pytest.raises(ValidationFailedError, match="required|reference"):
        validate_policy(kind, "STANDARD", policy)
