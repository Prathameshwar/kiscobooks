"""Versioned company starter definitions; creating a type never enables its effects."""

from functools import lru_cache
from typing import Any

from voucher_execution.invoice import InvoicePolicy
from voucher_execution.money import MoneyPolicy
from voucher_execution.stock import STOCK_PROFILES, StockPolicy

from vouchers.domain.configuration import validate_policy
from vouchers.schemas.configuration import (
    JobProcessConfiguration,
    ManufacturingConfiguration,
    MoneyConfiguration,
    OrderPolicy,
    Policy,
    TypeCreate,
)

# Every catalogue a company may have been provisioned from, oldest first. An earlier recipe is
# never edited: a company that still holds it untouched is recognised by its hash and follows the
# current one (see `tasks.company_defaults`). v2 changed the Journal and note recipes; v3 lets the
# Purchase account bill take service supplies, which a supplier bill with GST is recorded on. v4
# removes defaults that blocked ordinary entry without protecting a figure: the Sales account
# invoice takes service supplies too, invoices may carry discounts and charges, Payment and
# Receipt may carry settlement adjustments, and narration and line descriptions are optional.
PREVIOUS_VERSION = "company-voucher-defaults-v1"
SECOND_VERSION = "company-voucher-defaults-v2"
THIRD_VERSION = "company-voucher-defaults-v3"
VERSION = "company-voucher-defaults-v4"
RELEASED_VERSIONS = (PREVIOUS_VERSION, SECOND_VERSION, THIRD_VERSION, VERSION)
FEATURES = frozenset({"inventory", "bom_definitions", "approval_workflow", "multi_currency"})


@lru_cache(maxsize=32)
def catalogue(features: frozenset[str], *, version: str = VERSION) -> tuple[TypeCreate, ...]:
    """Use native defaults for limits; explicit values express each type's purpose."""
    definitions: list[TypeCreate] = []
    if version not in RELEASED_VERSIONS:
        raise ValueError("unsupported company voucher catalogue version")

    def add(code: str, name: str, kind: str, profile: str = "STANDARD", /, **rules: Any) -> None:
        policy = Policy.model_validate(
            {
                "schema_version": 2,
                "approval_required": "approval_workflow" in features,
                "self_approval_allowed": False,
                **rules,
            }
        )
        validate_policy(kind, profile, policy)
        definitions.append(
            TypeCreate(code=code, name=name, kind=kind, profile=profile, policy=policy)
        )

    current = version == VERSION
    # Narration is optional from v4; earlier recipes keep the rule they were provisioned with.
    narrated = not current
    # From v4 an invoice may carry discounts and charges; the calculation still bounds them.
    adjustable = {"manual_discounts_allowed": True, "charges_allowed": True} if current else {}
    account_mode = {"allowed_modes": ["ACCOUNTS"], "default_mode": "ACCOUNTS"}
    item_mode = {"allowed_modes": ["ITEMS"], "default_mode": "ITEMS"}
    for kind, code, name, purposes in (
        ("CONTRA", "CTR", "Contra", {"TRANSFER"}),
        ("JOURNAL", "JRN", "Journal", {"GENERAL", "BILL_ADJUSTMENT"}),
        ("PAYMENT", "PAY", "Payment", {"GENERAL", "SETTLEMENT", "REFUND"}),
        ("RECEIPT", "REC", "Receipt", {"GENERAL", "SETTLEMENT", "REFUND"}),
        ("PAYMENT", "PAY_ADV", "Supplier Advance", {"ADVANCE"}),
        ("RECEIPT", "REC_ADV", "Customer Advance", {"ADVANCE"}),
    ):
        add(
            code,
            name,
            kind,
            "ADVANCE" if purposes == {"ADVANCE"} else "STANDARD",
            **account_mode,
            required_sections=(
                [] if kind == "JOURNAL" and version != PREVIOUS_VERSION else ["ACCOUNTS"]
            ),
            forbidden_sections=["ITEMS"],
            narration_required=narrated and kind == "JOURNAL",
            **(
                {"allowed_party_roles": ["SUPPLIER" if kind == "PAYMENT" else "CUSTOMER"]}
                if purposes == {"ADVANCE"}
                else {}
            ),
            financial=MoneyPolicy.model_validate(
                {"foreign_currency_allowed": "multi_currency" in features}
                # Stated only from v4: an explicit False would change v1-v3 recipe hashes.
                | (
                    {"settlement_adjustments_allowed": kind in {"PAYMENT", "RECEIPT"}}
                    if current
                    else {}
                )
            ),
            money=MoneyConfiguration.model_validate({"allowed_purposes": purposes}),
        )

    for kind, prefix, label, role in (
        ("PURCHASE", "PUR", "Purchase", "SUPPLIER"),
        ("SALES", "SAL", "Sales", "CUSTOMER"),
    ):
        for suffix, description, mode, supplies in (
            (
                "ACC",
                "Account Bill" if kind == "PURCHASE" else "Account Invoice",
                "ACCOUNTS",
                # GST is recorded on service supplies; plain bills and invoices use ACCOUNT.
                ["ACCOUNT", "SERVICE"]
                if current or (kind == "PURCHASE" and version == THIRD_VERSION)
                else ["ACCOUNT"],
            ),
            (
                "PRD",
                "Product Bill" if kind == "PURCHASE" else "Product Invoice",
                "ITEMS",
                ["GOODS", "SERVICE"],
            ),
            (
                "MIX",
                "Mixed Bill" if kind == "PURCHASE" else "Mixed Invoice",
                "MIXED",
                ["ACCOUNT", "GOODS", "SERVICE"],
            ),
        ):
            required = ["PARTIES", "ACCOUNTS"]
            if kind == "PURCHASE":
                required.append("REFERENCES")
            if mode == "ITEMS":
                required.append("ITEMS")
            add(
                prefix + "_" + suffix,
                label + " - " + description,
                kind,
                allowed_modes=[mode],
                default_mode=mode,
                allowed_party_roles=[role],
                max_parties=1,
                required_sections=required,
                forbidden_sections=["ITEMS"] if mode == "ACCOUNTS" else [],
                supplier_reference_required=kind == "PURCHASE",
                line_description_required=not current,
                invoice=InvoicePolicy.model_validate(
                    {"allowed_supply_kinds": supplies} | adjustable
                ),
            )

    for kind, code, name, role in (
        ("CREDIT_NOTE", "CRN", "Credit Note", "CUSTOMER"),
        ("DEBIT_NOTE", "DBN", "Debit Note", "SUPPLIER"),
    ):
        add(
            code,
            name,
            kind,
            allowed_party_roles=[role],
            max_parties=1,
            required_sections=["PARTIES", "ACCOUNTS"]
            + (["REFERENCES"] if version == PREVIOUS_VERSION else []),
            narration_required=narrated,
            invoice=InvoicePolicy.model_validate(adjustable),
        )

    add(
        "PROFORMA",
        "Pro Forma Invoice",
        "SALES",
        "PRO_FORMA",
        allowed_party_roles=["CUSTOMER"],
        max_parties=1,
        required_sections=["PARTIES"],
    )
    for kind, code, name, profile, purpose, role in (
        ("SALES_ORDER", "SO", "Sales Order", "STANDARD", "SALE", "CUSTOMER"),
        ("SALES_ORDER", "QUOTE", "Quotation", "QUOTATION", "QUOTE", "CUSTOMER"),
        ("PURCHASE_ORDER", "PO", "Purchase Order", "STANDARD", "PURCHASE", "SUPPLIER"),
    ):
        add(
            code,
            name,
            kind,
            profile,
            **item_mode,
            allowed_party_roles=[role],
            max_parties=1,
            required_sections=["PARTIES", "ITEMS"],
            order=OrderPolicy.model_validate({"allowed_purposes": [purpose]}),
        )
    add("MEMO", "Memorandum", "MEMORANDUM", narration_required=narrated)
    add(
        "RVJ",
        "Reversing Journal",
        "REVERSING_JOURNAL",
        **account_mode,
        narration_required=narrated,
    )

    if "inventory" in features:
        for action, code, name in (
            ("RECEIPT", "GRN", "Goods Receipt Note"),
            ("DISPATCH", "DN", "Delivery Note"),
            ("CUSTOMER_RETURN", "RIN", "Rejections In"),
            ("SUPPLIER_RETURN", "ROUT", "Rejections Out"),
            ("OPENING", "STK_OPEN", "Opening Stock"),
            ("TRANSFER", "STK_TRF", "Stock Transfer"),
            ("TRANSFER_DISPATCH", "STK_SEND", "Stock Transfer Dispatch"),
            ("TRANSFER_RECEIPT", "STK_RECV", "Stock Transfer Receipt"),
            ("COUNT", "STK_COUNT", "Physical Stock Count"),
        ):
            kind, profile = STOCK_PROFILES[action]
            add(
                code,
                name,
                kind,
                profile,
                **item_mode,
                required_sections=["ITEMS"],
                narration_required=narrated,
                stock=StockPolicy(),
            )
        add(
            "DC",
            "Delivery Challan",
            "DELIVERY_NOTE",
            "DELIVERY_CHALLAN",
            **item_mode,
            required_sections=["PARTIES", "ITEMS"],
            narration_required=narrated,
        )
        for code, name, purpose in (
            ("REQ_PUR", "Purchase Requisition", "PROCURE"),
            ("REQ_MAT", "Material Requisition", "INTERNAL_ISSUE"),
        ):
            add(
                code,
                name,
                "STOCK_JOURNAL",
                "REQUISITION",
                **item_mode,
                required_sections=["ITEMS"],
                narration_required=narrated,
                order=OrderPolicy.model_validate({"allowed_purposes": [purpose]}),
            )
        for kind, code, name, role in (
            ("MATERIAL_IN", "MAT_IN_P", "Job Work Return In", "PRINCIPAL"),
            ("MATERIAL_OUT", "MAT_OUT_P", "Job Work Material Out", "PRINCIPAL"),
            ("MATERIAL_IN", "MAT_IN_W", "Customer Material In", "WORKER"),
            ("MATERIAL_OUT", "MAT_OUT_W", "Customer Material Return Out", "WORKER"),
            ("JOB_WORK_IN_ORDER", "JWI", "Job Work In Order", "WORKER"),
            ("JOB_WORK_OUT_ORDER", "JWO", "Job Work Out Order", "PRINCIPAL"),
        ):
            add(
                code,
                name,
                kind,
                **item_mode,
                required_sections=["PARTIES", "ITEMS"],
                narration_required=narrated,
                allowed_party_roles=["PRINCIPAL" if role == "WORKER" else "WORKER"],
                job_process=JobProcessConfiguration.model_validate(
                    {"role": role, "order_required": kind in {"MATERIAL_IN", "MATERIAL_OUT"}}
                ),
            )
        if "bom_definitions" in features:
            add(
                "MFG",
                "Manufacturing Journal",
                "STOCK_JOURNAL",
                "MANUFACTURING",
                **item_mode,
                required_sections=["ITEMS"],
                narration_required=narrated,
                manufacturing=ManufacturingConfiguration(),
            )
    return tuple(definitions)
