"""Resolve authoritative invoice facts before invoking the sole calculator."""

import hashlib
import uuid
from dataclasses import asdict
from fractions import Fraction
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import (
    InvoiceCalculationDetail,
    InvoicePreviewCommand,
    discount_policy_violation,
    sales_policy_violation,
)

from accounting.api.auth import Access
from accounting.domain.invoice_calculation import Component, Quantity, Supply, calculate, money
from accounting.domain.invoice_deals import priced_amount
from accounting.domain.invoice_discounts import enforce_discount_limits
from accounting.domain.invoice_landed_cost import landed_cost
from accounting.domain.invoice_readiness import posting_problem
from accounting.models.masters import Account, AccountGroup, AccountHead, PartyRole
from accounting.resources import BY_NAME
from accounting.tasks import allocation_targets
from accounting.tasks.access import authorize
from accounting.tasks.finance_records import require_fields
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.invoice_goods import GoodsFacts, check_line, inventory_account
from accounting.tasks.invoice_mappings import resolve as resolve_mappings
from accounting.tasks.invoice_tax import resolve as resolve_tax


async def preview(
    db: AsyncSession,
    access: Access,
    request: InvoicePreviewCommand,
    *,
    posting: bool = False,
    goods: GoodsFacts | None = None,
) -> InvoiceCalculationDetail:
    access.context.assert_current(access.actor, request.company_id)
    if (access.actor.tenant_id, access.actor.user_id) != (request.tenant_id, request.actor_user_id):
        raise PermissionDeniedError("invoice actor scope differs")
    access.actor.require_scope(
        "vouchers.post" if posting else "vouchers.read",
        target=ScopePath(company_id=request.company_id),
    )
    authorize(access, BY_NAME["account"], "read")
    facts = financial_context(access)
    if (
        facts.configuration_hash != request.company_configuration_hash
        or request.currency != access.context.base_currency
    ):
        raise ConflictError("invoice company configuration or currency is unsupported")
    body = request.invoice
    if request.kind == "SALES" and (violation := sales_policy_violation(body, request.policy)):
        raise ValidationFailedError(violation)
    if violation := discount_policy_violation(body, request.policy):
        raise ValidationFailedError(violation)
    if body.exchange_rate != 1:
        raise ValidationFailedError("base-currency invoice requires a unit exchange rate")
    accounts = {}
    for identity, version in {
        (body.party_account_id, body.party_account_version),
        *((line.account_id, line.account_version) for line in body.supplies),
        *((row.account_id, row.account_version) for row in body.components if row.account_id),
        *((row.account_id, row.account_version) for row in body.tenders),
        *(
            ([(body.rounding_account_id, body.rounding_account_version)])
            if body.rounding_account_id
            else []
        ),
    }:
        account = await company_object(db, Account, identity, company_id=request.company_id)
        require_fields(
            access,
            "account",
            {
                "kind",
                "status",
                "posting_policy",
                "party_role",
                "party_id",
                "currency",
                "currency_mode",
                "group_id",
            },
            row=account,
        )
        if account.row_version != version or account.status != "ACTIVE":
            raise ConflictError("invoice account changed or is inactive")
        if account.currency_mode == "FIXED" and account.currency != request.currency:
            raise ValidationFailedError("invoice currency differs from the selected account")
        accounts[identity] = account
    party = accounts[body.party_account_id]
    role = "CUSTOMER" if request.kind in {"SALES", "CREDIT_NOTE"} else "SUPPLIER"
    if party.kind != "PARTY" or party.party_role != role:
        raise ValidationFailedError("invoice party account has the wrong role")
    await require_sole_party_ledger(db, party)
    goods_keys = {line.line_key for line in body.supplies if line.supply_kind == "GOODS"}
    if goods_keys:
        # B24: goods are billed with their stock lines and post to the inventory account.
        if goods is None or request.stock is None:
            raise ValidationFailedError("goods are billed with their stock lines")
        inventory = await inventory_account(db, request.company_id, request.posting_date)
        for line in body.supplies:
            if line.supply_kind == "GOODS":
                check_line(line, goods, inventory)
    taxes = await resolve_tax(db, access, request, party, goods)
    policy = request.policy
    supplies = []
    groups = {}
    group_evidence = {}
    for identity in {accounts[line.account_id].group_id for line in body.supplies}:
        group = await company_object(db, AccountGroup, identity, company_id=request.company_id)
        require_fields(access, "account_group", {"head_id", "status"}, row=group)
        head = await company_object(db, AccountHead, group.head_id, company_id=request.company_id)
        require_fields(access, "account_head", {"nature"}, row=head)
        if group.status != "ACTIVE":
            raise ValidationFailedError("invoice supply account group must be active")
        groups[identity] = head.nature
        group_evidence[identity] = {
            "group_id": str(group.id),
            "group_version": group.row_version,
            "head_id": str(head.id),
            "head_version": head.row_version,
            "nature": head.nature,
        }
    for line in body.supplies:
        if (
            line.supply_kind not in policy.allowed_supply_kinds
            or line.price_basis not in policy.allowed_price_bases
        ):
            raise ValidationFailedError("invoice supply is not configured")
        quantities = {row.basis: row for row in line.quantities}
        actual = quantities.get("ACTUAL")
        billed = quantities.get("BILLED")
        if (
            actual is not None
            and billed is not None
            and (
                actual.unit_id != billed.unit_id
                or (line.free_purpose == "NONE" and actual.quantity != billed.quantity)
            )
        ):
            raise ValidationFailedError("invoice actual and billed quantities are inconsistent")
        if line.supply_kind != "GOODS" and (
            accounts[line.account_id].kind != "GENERAL"
            or accounts[line.account_id].posting_policy != "MANUAL_ALLOWED"
        ):
            # Goods post to the stock policy's inventory account, checked by check_line.
            raise ValidationFailedError("supply lines require general posting accounts")
        allowed_natures = (
            policy.sales_supply_natures if role == "CUSTOMER" else policy.purchase_supply_natures
        )
        if groups[accounts[line.account_id].group_id] not in allowed_natures:
            raise ValidationFailedError(
                "supply account group is not configured for this invoice direction"
            )
        if line.free_purpose != "NONE":
            raise ConflictError("free/deal preview requires published commercial and tax evidence")
        amount = line.amount
        if line.unit_price is not None:
            billed_units = [q for q in line.quantities if q.basis == "BILLED"]
            if len(billed_units) != 1:
                raise ValidationFailedError("unit prices require billed quantity evidence")
            amount = priced_amount(
                line.unit_price,
                billed_units[0].quantity,
                line.price_denominator,
                precision=facts.amount_precision,
                rounding_mode=facts.rounding_mode.upper(),
            )
            if amount != line.amount:
                raise ValidationFailedError("entered line amount differs from unit pricing")
        supplies.append(
            Supply(
                str(line.line_key),
                amount,
                line.price_basis == "GROSS_INCL_TAX",
                tuple(Quantity(q.basis, q.quantity, str(q.unit_id)) for q in line.quantities),
                taxes[line.line_key].components,
            )
        )
    components = []
    for account_id in {row.account_id for row in body.components if row.account_id} | (
        {body.rounding_account_id} if body.rounding_account_id else set()
    ):
        account = accounts[account_id]
        if account.kind != "GENERAL" or account.posting_policy != "MANUAL_ALLOWED":
            raise ValidationFailedError(
                "charge and rounding accounts require general posting accounts"
            )
    for settlement in body.tenders:
        account = accounts[settlement.account_id]
        if account.kind not in {"CASH", "BANK"} or account.posting_policy != "MANUAL_ALLOWED":
            raise ValidationFailedError("invoice tenders require a cash or bank posting account")
        if (settlement.tender.mode == "CASH") != (
            account.kind == "CASH"
        ) or settlement.tender.currency != request.currency:
            raise ValidationFailedError("invoice tender mode or currency differs from its account")
    for component in body.components:
        if (component.tax_targets or component.tax_allocation_basis is not None) and (
            not policy.independent_tax_allocation_allowed
        ):
            raise ValidationFailedError("independent tax allocation is not configured")
        if (
            component.scope not in policy.allowed_scopes
            or component.input_kind not in policy.allowed_component_inputs
            or component.amount_basis not in policy.allowed_price_bases
        ):
            raise ValidationFailedError("component recipe is not configured")
        if (component.effect == "DEDUCT" and not policy.manual_discounts_allowed) or (
            component.effect == "ADD" and not policy.charges_allowed
        ):
            raise ValidationFailedError("invoice component is not configured")
        if goods_keys & {*component.targets, *component.cost_targets}:
            # Charges on goods are capitalised into their landed cost by value (D02).
            if (
                component.account_id is not None
                or component.commercial_treatment != "COUNTERPARTY"
                or component.cost_targets
            ):
                raise ValidationFailedError(
                    "a charge on goods is part of their cost; remove its separate account"
                )
            if component.effect == "ADD" and (
                not set(component.targets) <= goods_keys or component.allocation_basis != "VALUE"
            ):
                raise ValidationFailedError(
                    "a charge on goods is spread over goods lines only, by value"
                )
        components.append(
            Component(
                str(component.component_key),
                tuple(map(str, component.targets)),
                component.value,
                component.effect,
                component.input_kind,
                tuple(map(str, component.dependencies)),
                component.amount_basis,
                component.allocation_basis,
                component.quantity_basis,
                str(component.unit_id) if component.unit_id else None,
                component.denominator,
                component.commercial_treatment == "COUNTERPARTY",
                component.tax_treatment == "ASSESSABLE",
                tuple(map(str, component.cost_targets)),
                component.cost_allocation_basis,
                tuple(map(str, component.tax_targets)),
                component.tax_allocation_basis,
            )
        )
    if len(components) > policy.max_components:
        raise ValidationFailedError("invoice exceeds configured component limit")
    result = calculate(
        tuple(supplies),
        tuple(components),
        precision=facts.amount_precision,
        rounding_mode=facts.rounding_mode.upper(),
        invoice_increment=body.rounding_increment,
    )
    enforce_discount_limits(body, policy, result)
    if len(result.allocations) > policy.max_allocations:
        raise ValidationFailedError("invoice exceeds configured allocation limit")
    if sum((Fraction(row.tender.amount) for row in body.tenders), Fraction()) > Fraction(
        result.payable
    ):
        raise ValidationFailedError("invoice tenders exceed the calculated payable")
    proposed_settlement = sum(
        (Fraction(row.tender.amount) for row in body.tenders), Fraction()
    ) + sum((Fraction(row.amount) for row in body.allocations), Fraction())
    if request.kind in {"SALES", "PURCHASE"} and proposed_settlement > Fraction(result.payable):
        raise ValidationFailedError("invoice settlements exceed the calculated payable")
    if request.kind == "SALES" and not policy.sales_credit_allowed:
        settled = sum((Fraction(row.tender.amount) for row in body.tenders), Fraction()) + sum(
            (Fraction(row.amount) for row in body.allocations), Fraction()
        )
        if settled != Fraction(result.payable):
            raise ValidationFailedError("non-credit sales require full settlement")
    if request.kind in {"SALES", "PURCHASE"}:
        # Notes are bound to their original party bill by validate_note_source at prepare.
        await allocation_targets.check_allocation_targets(
            db,
            access,
            body.allocations,
            posting_date=request.posting_date,
            new_bills={
                body.party_line_key: allocation_targets.NewBill(
                    body.party_account_id, request.currency
                )
            },
        )
    difference = None
    if body.supplier_declared_total is not None:
        if request.kind not in {"PURCHASE", "DEBIT_NOTE"}:
            raise ValidationFailedError(
                "supplier-declared totals require a purchase or supplier note"
            )
        difference = money(Fraction(body.supplier_declared_total) - Fraction(result.payable), 4)
        if abs(Fraction(difference)) > Fraction(policy.supplier_difference_limit) or (
            difference and not body.supplier_difference_reason
        ):
            raise ValidationFailedError(
                "supplier total difference requires a configured tolerance and reason"
            )
    source_lines = {line.line_key: line for line in body.supplies}
    evidence = tuple(
        [
            taxes[key].evidence
            | {
                "account_group": group_evidence[accounts[source_lines[key].account_id].group_id],
                "posting_mappings": await resolve_mappings(
                    db, access, request.kind, taxes[key].evidence
                ),
            }
            for key in sorted(taxes, key=str)
        ]
    )
    data: dict[str, Any] = asdict(result)
    data["calculation_version"] = data.pop("version")
    by_key = {row.key: row for row in result.lines}
    for row in data["lines"]:
        if uuid.UUID(row["key"]) in goods_keys:
            line_result = by_key[row["key"]]
            row["stock_cost"] = landed_cost(
                line_result.commercial,
                line_result.taxes,
                claimable=taxes[uuid.UUID(row["key"])].evidence.get("credit_state")
                != "INELIGIBLE",
            )
    output = InvoiceCalculationDetail.model_validate(
        data
        | {
            "currency": request.currency,
            "calculation_hash": "0" * 64,
            "tax_evidence": evidence,
            "supplier_difference": difference,
        }
    )
    calculation_identity = {
        "tenant_id": str(request.tenant_id),
        "company_id": str(request.company_id),
        "kind": request.kind,
        "profile": request.profile,
        "configuration_hash": request.configuration_hash,
        "company_configuration_hash": request.company_configuration_hash,
        "document_date": request.document_date.isoformat(),
        "posting_date": request.posting_date.isoformat(),
        # Acceptance stores the computed payable on the next voucher revision. It is
        # output evidence, not a new commercial input, so posting must hash the same
        # calculation that was offered for acceptance on the draft.
        "invoice": body.model_dump(
            mode="json", exclude={"accepted_calculation_hash"}
        ) | {"payable_total": None},
        "policy": policy.model_dump(mode="json"),
        "result": output.model_dump(mode="json", exclude={"calculation_hash"}),
    }
    if problem := posting_problem(request.kind, request.document_date, body, output):
        # A calculation that posting must refuse is never offered for acceptance.
        raise ValidationFailedError(problem)
    digest = hashlib.sha256(canonical_json(calculation_identity, maximum_bytes=1048576)).hexdigest()
    return output.model_copy(update={"calculation_hash": digest})


async def require_sole_party_ledger(db: AsyncSession, account: Account) -> None:
    """A bill credits the party's one ledger for its active role (party-ledger PL-D03, PL-D06)."""
    if account.party_id is None:
        raise ValidationFailedError("invoice party account is not linked to a party")
    role = await db.scalar(
        select(PartyRole.status).where(
            PartyRole.company_id == account.company_id,
            PartyRole.party_id == account.party_id,
            PartyRole.role == account.party_role,
        )
    )
    if role != "ACTIVE":
        raise ConflictError("the party's role for this invoice is not active")
    ledgers = await db.scalar(
        select(func.count(Account.id)).where(
            Account.company_id == account.company_id,
            Account.kind == "PARTY",
            Account.party_id == account.party_id,
            Account.party_role == account.party_role,
            Account.status.in_(("DRAFT", "ACTIVE")),
        )
    )
    if ledgers != 1:
        raise ConflictError("the party has more than one ledger for this role; repair it first")
