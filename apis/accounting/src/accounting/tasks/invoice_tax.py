"""Resolve dated native invoice tax recipes from company and owner-controlled masters.

The v2 boundary is deliberately separate from legacy posting-date tax requests.
It validates recipes through the shared GST mechanism; the invoice calculator applies
them once to its final commercial bases. No caller-supplied rate is accepted.
"""

import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, cast

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.tax_calc import TaxLine, TaxRequest, compute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import InvoicePreviewCommand, InvoiceSupply, InvoiceTaxContext

from accounting.api.auth import Access
from accounting.domain import voucher_tax as rules
from accounting.domain.invoice_calculation import Tax
from accounting.domain.invoice_tax_dates import service_tax_point
from accounting.models.masters import Account, PartyTaxRegistration
from accounting.models.tax_replica import (
    TaxClassificationReplica,
    TaxRateComponentReplica,
    TaxRateReplica,
    TaxRuleReplica,
)
from accounting.schemas.voucher_tax import TaxParty
from accounting.tasks.finance_records import require_fields
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.invoice_goods import GoodsFacts
from accounting.tasks.voucher_tax import (
    Outcome,
    _company,
    _components,
    _defaults,
    _party,
    utgst_states,
)


@dataclass(frozen=True)
class ResolvedTax:
    components: tuple[Tax, ...]
    evidence: dict[str, Any]


async def resolve_line(
    db: AsyncSession,
    access: Access,
    request: InvoicePreviewCommand,
    party_account: Account,
    line: InvoiceSupply,
    context: InvoiceTaxContext,
    goods: GoodsFacts | None = None,
) -> ResolvedTax:
    direction: rules.Direction = "SALE" if request.kind in {"SALES", "CREDIT_NOTE"} else "PURCHASE"
    if context.withholding_section_id is not None:
        raise ConflictError("invoice withholding requires its resolved statutory event")
    if context.payment_date is not None:
        raise ValidationFailedError(
            "payments require allocated consideration and tax-event evidence"
        )
    if line.supply_kind == "GOODS":
        if goods is None or request.kind != "PURCHASE":
            raise ValidationFailedError("goods are billed on a Purchase bill with its stock lines")
        return await resolve_goods_line(db, access, request, party_account, line, context, goods)
    if context.profile == "INDIA_DOMESTIC_GOODS":
        raise ValidationFailedError("the goods GST profile applies to goods lines only")
    if context.profile == "UNTAXED_ACCOUNT":
        defaults = await _defaults(db, access, {line.account_id}, direction, request.document_date)
        default = defaults.get(line.account_id)
        declared_no_tax_purchase = request.kind == "PURCHASE" and line.supply_kind == "ACCOUNT"
        if (default is not None and default.treatment != "NON_GST") or (
            access.context.registrations and default is None and not declared_no_tax_purchase
        ):
            raise ValidationFailedError(
                "tax-bearing or unclassified supplies require their statutory profile"
            )
        return ResolvedTax(
            (),
            {
                "line_key": str(line.line_key),
                "profile": context.profile,
                "date_contract_version": 2,
                "resolution_date": request.document_date.isoformat(),
                "default_id": str(default.id) if default else None,
                "default_version": default.row_version if default else None,
                "treatment": "NON_GST",
                "credit_state": "NOT_APPLICABLE",
            },
        )
    if request.kind not in {"SALES", "PURCHASE"}:
        raise ConflictError("tax notes require original posted component evidence")
    if line.supply_kind != "SERVICE" or context.service_completion_date is None:
        raise ValidationFailedError("ordinary service tax requires a service and completion date")
    if context.company_registration_id is None or context.place_of_supply is None:
        raise ValidationFailedError(
            "service tax requires the company registration and place of supply"
        )
    reverse = context.profile == "INDIA_DOMESTIC_SERVICE_RCM"
    if reverse and direction != "PURCHASE":
        raise ValidationFailedError("recipient RCM requires a purchase")
    invoice_date = request.document_date
    if direction == "PURCHASE":
        if context.supplier_invoice_date is None or context.supplier_invoice_number is None:
            raise ValidationFailedError(
                "purchase tax requires the supplier invoice identity and date"
            )
        invoice_date = context.supplier_invoice_date
    point = service_tax_point(
        invoice=invoice_date, supplied=context.service_completion_date, reverse_charge=reverse
    )
    on = point.tax_point_date
    defaults = await _defaults(db, access, {line.account_id}, direction, on)
    default = defaults.get(line.account_id)
    if default is None:
        raise ValidationFailedError("service has no account tax default at its legal tax point")
    require_fields(access, "account_tax_default", {"code_system", "code"}, row=default)
    if default.supply_kind != "SERVICE" or default.code_system != "SAC":
        raise ValidationFailedError("ordinary service profile requires a service SAC default")
    if default.rcm_applicable != reverse:
        raise ValidationFailedError("the RCM profile differs from the authoritative tax default")
    outcome = Outcome(request.kind, direction, on, request.currency)
    tax_party = TaxParty(
        company_registration_id=context.company_registration_id,
        party_registration_id=context.party_registration_id,
        place_of_supply=context.place_of_supply,
    )
    company = _company(access, tax_party, on, outcome)
    party = await _party(db, access, party_account.party_id, tax_party, on, outcome)
    outcome.require_ready()
    if company is None or company.state is None:
        raise ValidationFailedError("company GST registration has no state")
    if party.type not in {"REGULAR", "UNREGISTERED"}:
        raise ValidationFailedError(
            "counterparty requires a separately supported statutory profile"
        )
    # No recipient self-invoice or unregistered-supplier RCM is inferred here.
    if direction == "PURCHASE" and party.type != "REGULAR":
        raise ValidationFailedError("this supplier-invoice profile requires a regular GST supplier")
    determination = rules.determine(
        direction,
        company.state,
        party.type,
        party.state,
        context.place_of_supply,
        utgst_states=utgst_states(),
    )
    if isinstance(determination, rules.TaxException):
        raise ValidationFailedError(determination.message)
    first, last = sorted((invoice_date, context.service_completion_date))
    transition = await db.scalar(
        select(TaxRateReplica.id)
        .where(
            TaxRateReplica.company_id == request.company_id,
            TaxRateReplica.rule_id == default.rule_id,
            TaxRateReplica.applicability == determination.context.value,
            TaxRateReplica.source_action != "WITHDRAW",
            TaxRateReplica.valid_from > first,
            TaxRateReplica.valid_from <= last,
        )
        .limit(1)
    )
    if transition is not None:
        raise ValidationFailedError(
            "service crosses a published rate change; allocated payment-date evidence is required"
        )
    resolved = await _components(db, access, default, determination, on, outcome, 1)
    outcome.require_ready()
    if resolved is None:
        raise ValidationFailedError("dated tax recipe is unresolved")
    components, source = resolved
    facts = financial_context(access)
    # Zero-value validation exercises component/context, cess, treatment and regime
    # constraints without introducing a second invoice-amount calculation.
    compute(
        TaxRequest(
            lines=(
                TaxLine(
                    str(line.line_key),
                    cast(Any, default.supply_kind),
                    Decimal(0),
                    cast(Any, default.treatment),
                    components,
                ),
            ),
            determination=determination,
            currency=request.currency,
            amount_precision=facts.amount_precision,
            may_charge_tax=company.may_charge if direction == "SALE" else True,
            rounding_mode=facts.rounding_mode,
        )
    )
    evidence: dict[str, Any] = {
        "line_key": str(line.line_key),
        "profile": context.profile,
        "date_contract_version": 2,
        "tax_point": {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in asdict(point).items()
        },
        "company_registration_id": str(context.company_registration_id),
        "party_registration_id": str(party.registration_id) if party.registration_id else None,
        "place_of_supply": context.place_of_supply,
        "supply_context": determination.context.value,
        "account_id": str(line.account_id),
        "default_id": str(default.id),
        "default_version": default.row_version,
        "sac": default.code,
        "treatment": default.treatment,
        "reverse_charge": reverse,
        "itc_eligibility": default.itc_eligibility,
        "credit_state": "NOT_APPLICABLE"
        if direction == "SALE"
        else "PENDING_EVIDENCE"
        if company.recover and default.itc_eligibility == "ELIGIBLE"
        else "INELIGIBLE",
        **source,
    }
    evidence["company_registration"] = {
        key: (company.registration or {}).get(key)
        for key in (
            "id",
            "tax_system",
            "regime",
            "jurisdiction_code",
            "registration_number",
            "valid_from",
            "valid_to",
        )
    }
    if party.registration_id is not None:
        registration = await company_object(
            db, PartyTaxRegistration, party.registration_id, company_id=request.company_id
        )
        protected = {
            "registration_number",
            "registration_type",
            "state_code",
            "valid_from",
            "valid_to",
        }
        require_fields(access, "party_tax_registration", protected, row=registration)
        evidence["party_registration"] = {
            "id": str(registration.id),
            "source_version": registration.row_version,
            **{
                key: value.isoformat() if hasattr(value, "isoformat") else value
                for key in protected
                if (value := getattr(registration, key)) is not None
            },
        }
    return await _recipe(
        db,
        request,
        source,
        components,
        evidence,
        item_kind="SERVICE",
        treatment=default.treatment,
        supplier_charged=not reverse,
        mismatch="published tax rule differs from the account classification",
    )


@dataclass(frozen=True)
class _ItemRule:
    """A purchased item's published bundle, read as a tax recipe source (``RuleSource``)."""

    treatment: str
    rule_id: uuid.UUID | None


async def resolve_goods_line(
    db: AsyncSession,
    access: Access,
    request: InvoicePreviewCommand,
    party_account: Account,
    line: InvoiceSupply,
    context: InvoiceTaxContext,
    goods: GoodsFacts,
) -> ResolvedTax:
    """Forward-charge GST on purchased goods from the item's published HSN bundle.

    The item's classification and rule come from Catalog's signed facts for the bill's
    stock date and are checked against Accounting's own replicas; the dated rates are
    Accounting's. The tax point of a supplier's goods invoice is its invoice date.
    """
    stock_line, item = goods.item(line)
    warehouse = goods.warehouses.get(stock_line.warehouse_id)
    if warehouse is None:
        raise ConflictError("the purchased goods warehouse facts are unavailable")
    if (
        warehouse.tax_registration_id is not None
        and context.company_registration_id != warehouse.tax_registration_id
    ):
        raise ValidationFailedError(
            "Choose the company tax registration configured for the goods receiving warehouse",
            fields={
                "company_registration_id": (
                    "The selected registration differs from the receiving warehouse"
                )
            },
        )
    base: dict[str, Any] = {
        "line_key": str(line.line_key),
        "profile": context.profile,
        "date_contract_version": 2,
        "account_id": str(line.account_id),
        "item_id": str(item.item_id),
        "item_version": item.item_version,
        "receiving_warehouse": {
            "warehouse_id": str(warehouse.warehouse_id),
            "row_version": warehouse.row_version,
            "country_code": warehouse.country_code,
            "state_code": warehouse.state_code,
            "tax_registration_id": str(warehouse.tax_registration_id)
            if warehouse.tax_registration_id
            else None,
            "address_line1": warehouse.address_line1,
            "address_line2": warehouse.address_line2,
            "city": warehouse.city,
            "postal_code": warehouse.postal_code,
        },
    }
    if context.profile == "UNTAXED_ACCOUNT":
        # A company without GST registration pays the supplier's GST as part of the price.
        if any(row.get("tax_system") == "gst_in" for row in access.context.registrations):
            raise ValidationFailedError(
                "a GST-registered company records purchased goods with their GST profile"
            )
        return ResolvedTax(
            (),
            base
            | {
                "resolution_date": request.document_date.isoformat(),
                "treatment": "NON_GST",
                "credit_state": "NOT_APPLICABLE",
            },
        )
    if context.profile != "INDIA_DOMESTIC_GOODS":
        raise ValidationFailedError("purchased goods use the goods GST profile")
    if context.company_registration_id is None or context.place_of_supply is None:
        raise ValidationFailedError(
            "goods GST requires the company registration and place of supply"
        )
    if context.supplier_invoice_date is None or context.supplier_invoice_number is None:
        raise ValidationFailedError("purchase tax requires the supplier invoice identity and date")
    fact = item.purchase_tax
    if fact is None:
        raise ValidationFailedError(
            "assign the product's purchase HSN classification and GST rule before billing it"
        )
    on = context.supplier_invoice_date
    classification = await db.scalar(
        select(TaxClassificationReplica).where(
            TaxClassificationReplica.company_id == request.company_id,
            TaxClassificationReplica.id == fact.classification_id,
        )
    )
    if (
        classification is None
        or classification.source_action == "WITHDRAW"
        or classification.code_system != "HSN"
        or classification.item_kind != "GOODS"
        or classification.code != fact.code
        or classification.valid_from > on
        or (classification.valid_to is not None and classification.valid_to < on)
    ):
        raise ValidationFailedError(
            "the product's HSN classification is not yet effective in Accounting on the invoice "
            "date; retry once it has been published"
        )
    outcome = Outcome(request.kind, "PURCHASE", on, request.currency)
    tax_party = TaxParty(
        company_registration_id=context.company_registration_id,
        party_registration_id=context.party_registration_id,
        place_of_supply=context.place_of_supply,
    )
    company = _company(access, tax_party, on, outcome)
    party = await _party(db, access, party_account.party_id, tax_party, on, outcome)
    outcome.require_ready()
    if company is None or company.state is None:
        raise ValidationFailedError("company GST registration has no state")
    if party.type != "REGULAR":
        raise ValidationFailedError("this supplier-invoice profile requires a regular GST supplier")
    determination = rules.determine(
        "PURCHASE",
        company.state,
        party.type,
        party.state,
        context.place_of_supply,
        utgst_states=utgst_states(),
    )
    if isinstance(determination, rules.TaxException):
        raise ValidationFailedError(determination.message)
    recipe = _ItemRule(fact.treatment, fact.rule_id)
    resolved = await _components(db, access, recipe, determination, on, outcome, 1)
    outcome.require_ready()
    if resolved is None:
        raise ValidationFailedError("dated tax recipe is unresolved")
    components, source = resolved
    facts = financial_context(access)
    compute(
        TaxRequest(
            lines=(
                TaxLine(
                    str(line.line_key),
                    cast(Any, "GOODS"),
                    Decimal(0),
                    cast(Any, fact.treatment),
                    components,
                ),
            ),
            determination=determination,
            currency=request.currency,
            amount_precision=facts.amount_precision,
            may_charge_tax=True,
            rounding_mode=facts.rounding_mode,
        )
    )
    claimable = company.recover and line.input_credit != "INELIGIBLE"
    evidence: dict[str, Any] = base | {
        # CGST s.12(2)(a): goods are supplied, for tax, on the date of their invoice.
        "tax_point": {
            "tax_point_date": on.isoformat(),
            "invoice_date": on.isoformat(),
            "legal_basis": "CGST_12_2_A",
        },
        "company_registration_id": str(context.company_registration_id),
        "party_registration_id": str(party.registration_id) if party.registration_id else None,
        "place_of_supply": context.place_of_supply,
        "supply_context": determination.context.value,
        "classification_id": str(fact.classification_id),
        "classification_version": fact.classification_version,
        "hsn": fact.code,
        "item_rule_version": fact.rule_version,
        "treatment": fact.treatment,
        "reverse_charge": False,
        "itc_eligibility": "ELIGIBLE" if line.input_credit != "INELIGIBLE" else "INELIGIBLE",
        "input_credit_reason": line.input_credit_reason,
        "credit_state": "PENDING_EVIDENCE" if claimable else "INELIGIBLE",
        **source,
    }
    evidence["company_registration"] = {
        key: (company.registration or {}).get(key)
        for key in (
            "id",
            "tax_system",
            "regime",
            "jurisdiction_code",
            "registration_number",
            "valid_from",
            "valid_to",
        )
    }
    return await _recipe(
        db,
        request,
        source,
        components,
        evidence,
        item_kind="GOODS",
        treatment=fact.treatment,
        supplier_charged=True,
        mismatch="the product's published GST rule differs from Accounting's copy",
    )


async def _recipe(
    db: AsyncSession,
    request: InvoicePreviewCommand,
    source: dict[str, Any],
    components: tuple[Any, ...],
    evidence: dict[str, Any],
    *,
    item_kind: str,
    treatment: str,
    supplier_charged: bool,
    mismatch: str,
) -> ResolvedTax:
    """The dated rule/rate replica rows behind ``components``, recorded as evidence."""
    if source["rule_id"] is None:
        return ResolvedTax((), evidence)
    rule = await db.scalar(
        select(TaxRuleReplica).where(
            TaxRuleReplica.company_id == request.company_id,
            TaxRuleReplica.id == uuid.UUID(source["rule_id"]),
        )
    )
    rate = await db.scalar(
        select(TaxRateReplica).where(
            TaxRateReplica.company_id == request.company_id,
            TaxRateReplica.id == uuid.UUID(source["rate_id"]),
        )
    )
    if rule is None or rate is None or rule.item_kind != item_kind or rule.treatment != treatment:
        raise ValidationFailedError(mismatch)
    rows = list(
        await db.scalars(
            select(TaxRateComponentReplica)
            .where(
                TaxRateComponentReplica.company_id == request.company_id,
                TaxRateComponentReplica.rate_id == rate.id,
            )
            .order_by(TaxRateComponentReplica.position, TaxRateComponentReplica.id)
            .limit(9)
        )
    )
    if len(rows) > 8 or len(rows) != len(components):
        raise ValidationFailedError("tax recipe exceeds the supported component bound")
    evidence.update(
        rule_version=rule.source_version,
        rate_version=rate.source_version,
        rule_sha256=rule.source_sha256,
        rate_sha256=rate.source_sha256,
        components=[
            {
                "id": str(row.id),
                "source_version": row.source_version,
                "code": row.component,
                "percentage": str(row.percentage),
                "rounding_mode": row.rounding_mode,
            }
            for row in rows
        ],
    )
    if any(row.kind != "PERCENT" or row.percentage is None for row in rows):
        raise ValidationFailedError("invoice GST requires percentage-based tax components")
    return ResolvedTax(
        tuple(
            Tax(
                str(row.id),
                row.component,
                cast(Decimal, row.percentage),
                supplier_charged=supplier_charged,
                rounding_mode=row.rounding_mode,
            )
            for row in rows
        ),
        evidence,
    )


async def resolve(
    db: AsyncSession,
    access: Access,
    request: InvoicePreviewCommand,
    party: Account,
    goods: GoodsFacts | None = None,
) -> dict[uuid.UUID, ResolvedTax]:
    return {
        line.line_key: await resolve_line(
            db, access, request, party, line, line.tax or request.invoice.tax, goods
        )
        for line in request.invoice.supplies
    }
