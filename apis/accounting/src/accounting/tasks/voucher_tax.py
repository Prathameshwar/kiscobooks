"""GST and TDS/TCS on journals and party documents (tax-accounting Phase 8).

Everything resolves by ``posting_date`` from local rows: account tax defaults, the Catalog GST
replica, posting mappings, party registrations and withholding masters, plus the signed Identity
company context. No synchronous cross-service call is made. The draft stores the request and
the resulting *Tax Analysis*; posting re-derives it and refuses on any difference, so a posted
voucher is never recomputed.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol, cast

from billing_platform.db.access import company_object
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.money import quantize_storage
from billing_platform.statutory import covers
from billing_platform.tax import may_charge_tax, registration_class
from billing_platform.tax_calc import (
    BuyerType,
    SupplyDetermination,
    TaxComponent,
    TaxComputation,
    TaxLine,
    TaxRequest,
    compute,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain import voucher_tax as rules
from accounting.domain.rules import INPUT_RECOVERING_REGIMES
from accounting.domain.tax_replica import WITHDRAW, effective_on
from accounting.domain.voucher_tax import Direction, Posting, Side, TaxedLine, TaxException
from accounting.domain.withholding import (
    CertificateTerms,
    ProfileTerms,
    RateTerms,
    WithholdingResult,
    resolve_withholding,
)
from accounting.models import masters as m
from accounting.models.fiscal import FiscalYear
from accounting.models.ledger import Journal, JournalLine
from accounting.models.tax_replica import TaxRateComponentReplica, TaxRateReplica, TaxRuleReplica
from accounting.models.voucher_tax import JournalTax
from accounting.resources import BY_NAME
from accounting.schemas.ledger import JournalCreate, JournalLineCreate
from accounting.schemas.subledger import SourceCreate, TaxPreviewRequest
from accounting.schemas.voucher_tax import (
    SourceTax,
    TaxExceptionItem,
    TaxParty,
    TaxPreview,
    TaxPreviewLine,
    VoucherTax,
)
from accounting.tasks.access import authorize, readable
from accounting.tasks.finance_records import require_fields
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.validation import registration_window, require_withholding_feature
from accounting.tasks.withholding import INPUTS as WITHHOLDING_INPUTS
from accounting.tasks.withholding import effective

ZERO = Decimal(0)
ONE = Decimal(1)
DEFAULT_FIELDS = {
    "account_id",
    "direction",
    "supply_kind",
    "rule_id",
    "treatment",
    "itc_eligibility",
    "rcm_applicable",
    "valid_from",
    "valid_to",
}
REGISTRATION_FIELDS = {
    "party_id",
    "scheme",
    "registration_type",
    "state_code",
    "valid_from",
    "valid_to",
}
MAPPING_FIELDS = {
    "purpose",
    "account_id",
    "currency",
    "valid_from",
    "valid_to",
    "company_registration_id",
}
_UTGST: frozenset[str] = frozenset()


def configure(states: Iterable[str]) -> None:
    """Install the UTGST-levying state codes from service configuration (reference data)."""
    global _UTGST
    _UTGST = frozenset(state for code in states if (state := rules.bare_state(code)))


def utgst_states() -> frozenset[str]:
    return _UTGST


@dataclass
class Outcome:
    """A voucher's resolved Tax Analysis; ``values`` are the ``journal_tax`` columns."""

    kind: str
    direction: Direction
    posting_date: dt.date
    currency: str
    exceptions: list[TaxException] = field(default_factory=list)
    lines: list[JournalLineCreate] = field(default_factory=list)
    purposes: list[str | None] = field(default_factory=list)
    line_count: int = 0
    taxable_value: Decimal = ZERO
    tax_total: Decimal = ZERO
    withholding_kind: str | None = None
    withholding_tax: Decimal | None = None
    party_amount: Decimal | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)

    def fail(self, code: str, message: str, line: int | None = None) -> None:
        self.exceptions.append(TaxException(code, message, line))

    @property
    def ready(self) -> bool:
        return not self.exceptions

    def require_ready(self) -> None:
        if self.exceptions:
            raise ValidationFailedError(
                "the voucher's tax analysis has unresolved exceptions",
                fields={item.code: item.message for item in self.exceptions},
            )

    def draft(self, body: JournalCreate | SourceCreate) -> JournalCreate:
        return JournalCreate(
            document_date=body.document_date,
            posting_date=body.posting_date,
            description=body.description,
            lines=self.lines,
        )


@dataclass(frozen=True)
class _Company:
    registration: dict[str, Any] | None
    state: str | None
    regime: str | None
    may_charge: bool
    recover: bool


@dataclass(frozen=True)
class _Party:
    party_id: uuid.UUID | None
    registration_id: uuid.UUID | None
    type: str
    state: str | None


def _line(
    account_id: uuid.UUID, side: Side, currency: str, amount: Decimal, label: str | None = None
) -> JournalLineCreate:
    return JournalLineCreate(
        account_id=account_id,
        side=side,
        currency=currency,
        amount=amount,
        exchange_rate=ONE,
        description=label,
    )


def _company(access: Access, tax: TaxParty, on: dt.date, outcome: Outcome) -> _Company | None:
    rows = [row for row in access.context.registrations if row.get("tax_system") == "gst_in"]

    def supplier(row: dict[str, Any]) -> bool:
        implied = registration_class("gst_in", str(row.get("regime")))
        return implied == "supplier" and row.get("registration_class", implied) == implied

    if tax.company_registration_id is not None:
        chosen = [row for row in rows if row.get("id") == str(tax.company_registration_id)]
        if not chosen or not supplier(chosen[0]):
            outcome.fail(
                "COMPANY_REGISTRATION_MISSING", "the company has no such supplier GST registration"
            )
            return None
        start, end = registration_window(chosen[0])
        if not covers(start, end, on):
            outcome.fail(
                "COMPANY_REGISTRATION_EXPIRED",
                "the company registration is not valid on the posting date",
            )
            return None
        registration = chosen[0]
    else:
        current = [row for row in rows if supplier(row) and covers(*registration_window(row), on)]
        if not current:
            outcome.fail(
                "COMPANY_REGISTRATION_MISSING",
                "the company has no supplier GST registration on the posting date",
            )
            return None
        if len(current) > 1:
            outcome.fail(
                "COMPANY_REGISTRATION_AMBIGUOUS",
                "the company has several GST registrations; name company_registration_id",
            )
            return None
        registration = current[0]
    regime = str(registration.get("regime"))
    try:
        charge = may_charge_tax("gst_in", regime)
    except ValidationFailedError:
        charge = False
    return _Company(
        registration,
        rules.bare_state(str(registration.get("jurisdiction_code") or "")),
        regime,
        charge,
        regime in INPUT_RECOVERING_REGIMES,
    )


async def _party(
    db: AsyncSession,
    access: Access,
    party_id: uuid.UUID | None,
    tax: TaxParty,
    on: dt.date,
    outcome: Outcome,
) -> _Party:
    stated = rules.bare_state(tax.party_state)
    if tax.party_registration_id is None:
        return _Party(party_id, None, BuyerType.UNREGISTERED.value, stated)
    row = await company_object(
        db, m.PartyTaxRegistration, tax.party_registration_id, company_id=access.context.company_id
    )
    require_fields(access, "party_tax_registration", REGISTRATION_FIELDS, row=row)
    if row.party_id != party_id or row.scheme != "GST_IN":
        outcome.fail(
            "PARTY_REGISTRATION_MISSING", "the registration is not this party's GST registration"
        )
    elif not covers(row.valid_from or dt.date.min, row.valid_to, on):
        outcome.fail(
            "PARTY_REGISTRATION_EXPIRED", "the party registration is not valid on the posting date"
        )
    kind = row.registration_type if row.registration_type in BuyerType.__members__ else "OTHER"
    return _Party(party_id, row.id, kind, rules.bare_state(row.state_code) or stated)


async def _defaults(
    db: AsyncSession,
    access: Access,
    accounts: set[uuid.UUID],
    direction: Direction,
    on: dt.date,
) -> dict[uuid.UUID, m.AccountTaxDefault]:
    if not accounts:
        return {}
    authorize(access, BY_NAME["account_tax_default"], "read")
    rows = list(
        await db.scalars(
            select(m.AccountTaxDefault)
            .where(
                m.AccountTaxDefault.company_id == access.context.company_id,
                m.AccountTaxDefault.account_id.in_(accounts),
                m.AccountTaxDefault.direction == direction,
                m.AccountTaxDefault.valid_from <= on,
                (m.AccountTaxDefault.valid_to.is_(None)) | (m.AccountTaxDefault.valid_to >= on),
            )
            .order_by(m.AccountTaxDefault.id)
            .limit(201)
        )
    )
    found: dict[uuid.UUID, m.AccountTaxDefault] = {}
    for row in rows:
        require_fields(access, "account_tax_default", DEFAULT_FIELDS, row=row)
        if row.account_id in found:
            raise ConflictError("account tax defaults overlap on the posting date")
        found[row.account_id] = row
    return found


class RuleSource(Protocol):
    """What a tax recipe is read from: an account's tax default, or a purchased item's bundle."""

    @property
    def treatment(self) -> str: ...

    @property
    def rule_id(self) -> uuid.UUID | None: ...


async def _components(
    db: AsyncSession,
    access: Access,
    default: RuleSource,
    determination: SupplyDetermination,
    on: dt.date,
    outcome: Outcome,
    sequence: int,
) -> tuple[tuple[TaxComponent, ...], dict[str, Any]] | None:
    """The rate components the default's rule applies on ``on`` in the supply's context."""
    evidence: dict[str, Any] = {"rule_id": None, "rate_id": None}
    if default.treatment in {"EXEMPT", "NON_GST"}:
        return (), evidence
    if default.rule_id is None:
        outcome.fail("RULE_MISSING", "the account tax default names no tax rule", sequence)
        return None
    company = access.context.company_id
    rule = await db.scalar(
        select(TaxRuleReplica).where(
            TaxRuleReplica.company_id == company, TaxRuleReplica.id == default.rule_id
        )
    )
    if rule is None:
        outcome.fail("RULE_MISSING", "the tax rule has not been replicated", sequence)
        return None
    if not rule.is_active:
        outcome.fail("RULE_INACTIVE", "the tax rule is withdrawn", sequence)
        return None
    rates = [
        row
        for row in await db.scalars(
            select(TaxRateReplica)
            .where(
                TaxRateReplica.company_id == company,
                TaxRateReplica.rule_id == rule.id,
                TaxRateReplica.applicability == determination.context.value,
                TaxRateReplica.source_action != WITHDRAW,
                TaxRateReplica.valid_from <= on,
                (TaxRateReplica.valid_to.is_(None)) | (TaxRateReplica.valid_to >= on),
            )
            .order_by(TaxRateReplica.id)
            .limit(2)
        )
        if effective_on(row.source_action, row.valid_from, row.valid_to, on)
    ]
    if not rates:
        outcome.fail(
            "RATE_MISSING",
            f"no {determination.context.value} rate applies on the posting date",
            sequence,
        )
        return None
    if len(rates) > 1:
        outcome.fail("RATE_AMBIGUOUS", "several rates apply on the posting date", sequence)
        return None
    rows = await db.scalars(
        select(TaxRateComponentReplica)
        .where(
            TaxRateComponentReplica.company_id == company,
            TaxRateComponentReplica.rate_id == rates[0].id,
        )
        .order_by(TaxRateComponentReplica.position, TaxRateComponentReplica.id)
        .limit(10)
    )
    components = tuple(
        TaxComponent(
            component=cast(Any, row.component),
            kind=cast(Any, row.kind),
            rounding_mode=cast(Any, row.rounding_mode),
            position=row.position,
            percentage=row.percentage,
            amount=row.amount,
            currency=row.currency,
            unit_id=row.unit_id,
            basis_quantity=row.basis_quantity,
        )
        for row in rows
    )
    evidence.update(rule_id=str(rule.id), rate_id=str(rates[0].id))
    return components, evidence


async def _mapping(
    db: AsyncSession,
    access: Access,
    purpose: str,
    registration_id: str | None,
    on: dt.date,
    cache: dict[str, uuid.UUID | None],
) -> uuid.UUID | None:
    if purpose in cache:
        return cache[purpose]
    row = await mapping_row(db, access, purpose, registration_id, on)
    cache[purpose] = row.account_id if row is not None else None
    return cache[purpose]


async def mapping_row(
    db: AsyncSession,
    access: Access,
    purpose: str,
    registration_id: str | None,
    on: dt.date,
) -> m.AccountPostingMapping | None:
    """Resolve one dated mapping; both legacy posting and invoice evidence use this rule."""
    spec = BY_NAME["account_posting_mapping"]
    authorize(access, spec, "read")
    if not MAPPING_FIELDS <= readable(access, spec):
        raise PermissionDeniedError("tax posting mappings are not readable")
    scope = (
        m.AccountPostingMapping.company_registration_id.is_(None)
        if registration_id is None
        else (m.AccountPostingMapping.company_registration_id == uuid.UUID(registration_id))
        | m.AccountPostingMapping.company_registration_id.is_(None)
    )
    rows = list(
        await db.scalars(
            select(m.AccountPostingMapping)
            .where(
                m.AccountPostingMapping.company_id == access.context.company_id,
                m.AccountPostingMapping.purpose == purpose,
                scope,
                m.AccountPostingMapping.currency == access.context.base_currency,
                m.AccountPostingMapping.valid_from <= on,
                (m.AccountPostingMapping.valid_to.is_(None))
                | (m.AccountPostingMapping.valid_to >= on),
            )
            .limit(2)
        )
    )
    return rows[0] if len(rows) == 1 else None


@dataclass
class _Gst:
    computation: TaxComputation | None
    taxed: list[TaxedLine]
    determination: SupplyDetermination | None
    company: _Company | None
    party: _Party
    reverse_charge: bool
    evidence: list[dict[str, Any]]


async def _gst(
    db: AsyncSession,
    access: Access,
    tax: TaxParty,
    party: _Party,
    outcome: Outcome,
    candidates: Sequence[tuple[int, uuid.UUID, Decimal]],
    defaults: dict[uuid.UUID, m.AccountTaxDefault],
) -> _Gst:
    """Resolve and compute GST for ``(sequence, account, value)`` taxable lines."""
    on, direction = outcome.posting_date, outcome.direction
    result = _Gst(None, [], None, None, party, False, [])
    company = _company(access, tax, on, outcome)
    result.company = company
    if company is None or company.state is None:
        if company is not None:
            outcome.fail("COMPANY_REGISTRATION_MISSING", "the company registration has no state")
        return result
    reverse = {
        direction == "PURCHASE" and defaults[account].rcm_applicable for _, account, _ in candidates
    }
    if len(reverse) > 1:
        outcome.fail(
            "MIXED_REVERSE_CHARGE", "reverse-charge and forward-charge lines need separate vouchers"
        )
        return result
    result.reverse_charge = reverse == {True}
    determined = rules.determine(
        direction,
        company.state,
        party.type,
        party.state,
        tax.place_of_supply,
        utgst_states=_UTGST,
    )
    if isinstance(determined, TaxException):
        outcome.exceptions.append(determined)
        return result
    result.determination = determined
    charges = (
        direction == "SALE"
        or result.reverse_charge
        or rules.supplier_charges(direction, party.type)
    )
    may_charge = company.may_charge if direction == "SALE" else charges
    lines: list[TaxLine] = []
    for sequence, account, value in candidates:
        default = defaults[account]
        resolved = await _components(db, access, default, determined, on, outcome, sequence)
        if resolved is None:
            continue
        components, evidence = resolved
        recover = (
            direction == "PURCHASE" and company.recover and default.itc_eligibility == "ELIGIBLE"
        )
        key = f"L{sequence}"
        lines.append(
            TaxLine(
                key=key,
                supply_kind=cast(Any, default.supply_kind),
                value=value,
                treatment=cast(Any, default.treatment),
                components=components if charges else (),
            )
        )
        result.taxed.append(TaxedLine(key, account, result.reverse_charge, recover))
        result.evidence.append(
            evidence
            | {
                "key": key,
                "sequence": sequence,
                "account_id": str(account),
                "default_id": str(default.id),
                "treatment": default.treatment,
                "supply_kind": default.supply_kind,
                "itc_eligibility": default.itc_eligibility,
                "reverse_charge": result.reverse_charge,
                "recover": recover,
            }
        )
    if outcome.exceptions:
        return result
    facts = financial_context(access)
    try:
        result.computation = compute(
            TaxRequest(
                lines=tuple(lines),
                determination=determined,
                currency=outcome.currency,
                amount_precision=facts.amount_precision,
                may_charge_tax=may_charge,
                rounding_mode=facts.rounding_mode,
                zero_rated_with_payment=tax.zero_rated_with_payment,
            )
        )
    except ValidationFailedError as exc:
        code = "REGIME_REFUSED" if "may not charge" in exc.message else "COMPUTATION_REFUSED"
        outcome.fail(code, exc.message)
    return result


async def _ytd(
    db: AsyncSession, access: Access, party_id: uuid.UUID, section_id: uuid.UUID, year: FiscalYear
) -> tuple[Decimal, Decimal]:
    company = access.context.company_id
    reversed_ids = select(Journal.reversal_of_id).where(
        Journal.company_id == company,
        Journal.status == "POSTED",
        Journal.reversal_of_id.is_not(None),
    )
    row = (
        await db.execute(
            select(func.sum(JournalTax.withholding_amount), func.sum(JournalTax.withholding_base))
            .join(
                Journal,
                (Journal.company_id == JournalTax.company_id)
                & (Journal.id == JournalTax.journal_id),
            )
            .where(
                JournalTax.company_id == company,
                JournalTax.party_id == party_id,
                JournalTax.withholding_section_id == section_id,
                Journal.status == "POSTED",
                Journal.posting_date >= year.start_date,
                Journal.posting_date <= year.end_date,
                Journal.id.not_in(reversed_ids),
            )
        )
    ).one()
    return (
        quantize_storage(Decimal(str(row[0] or 0))),
        quantize_storage(Decimal(str(row[1] or 0))),
    )


async def _consumed(db: AsyncSession, access: Access, certificate_id: uuid.UUID) -> Decimal:
    company = access.context.company_id
    reversed_ids = select(Journal.reversal_of_id).where(
        Journal.company_id == company,
        Journal.status == "POSTED",
        Journal.reversal_of_id.is_not(None),
    )
    value = await db.scalar(
        select(func.sum(JournalTax.certificate_base))
        .join(
            Journal,
            (Journal.company_id == JournalTax.company_id) & (Journal.id == JournalTax.journal_id),
        )
        .where(
            JournalTax.company_id == company,
            JournalTax.certificate_id == certificate_id,
            Journal.status == "POSTED",
            Journal.id.not_in(reversed_ids),
        )
    )
    return quantize_storage(Decimal(str(value or 0)))


async def _withholding(
    db: AsyncSession,
    access: Access,
    section_id: uuid.UUID,
    party_id: uuid.UUID,
    base: Decimal,
    outcome: Outcome,
) -> tuple[m.WithholdingSection, WithholdingResult] | None:
    for name, fields in WITHHOLDING_INPUTS.items():
        require_fields(access, name, fields)
    company = access.context.company_id
    section = await company_object(db, m.WithholdingSection, section_id, company_id=company)
    require_fields(
        access, "withholding_section", WITHHOLDING_INPUTS["withholding_section"], row=section
    )
    require_withholding_feature(access, section.kind)
    expected = "TCS" if outcome.kind == "INVOICE" else "TDS"
    if section.kind != expected or section.status != "ACTIVE":
        outcome.fail("WITHHOLDING_KIND", f"{outcome.kind} requires an active {expected} section")
        return None
    on = outcome.posting_date
    year = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.company_id == company,
            FiscalYear.start_date <= on,
            FiscalYear.end_date >= on,
        )
    )
    if year is None:
        outcome.fail("FISCAL_YEAR_MISSING", "no fiscal year contains the posting date")
        return None
    ytd_amount, ytd_base = await _ytd(db, access, party_id, section.id, year)
    rates = await effective(db, access, m.WithholdingRate, on, section_id=section.id)
    profiles = await effective(
        db, access, m.PartyWithholdingProfile, on, party_id=party_id, kind=section.kind
    )
    certificates = await effective(
        db, access, m.WithholdingCertificate, on, party_id=party_id, section_id=section.id
    )
    consumed = await _consumed(db, access, certificates[0].id) if len(certificates) == 1 else ZERO
    facts = financial_context(access)
    try:
        result = resolve_withholding(
            kind=section.kind,
            rates=[
                RateTerms(
                    row.id,
                    row.deductee_type,
                    row.rate_percent,
                    row.no_pan_rate_percent,
                    row.single_transaction_threshold,
                    row.aggregate_annual_threshold,
                    row.threshold_basis,
                    row.valid_from,
                    row.valid_to,
                )
                for row in rates
            ],
            profiles=[
                ProfileTerms(
                    row.id,
                    row.kind,
                    row.deductible,
                    row.deductee_type,
                    row.pan_status,
                    row.valid_from,
                    row.valid_to,
                )
                for row in profiles
            ],
            certificates=[
                CertificateTerms(
                    row.id, row.rate_percent, row.amount_limit, row.valid_from, row.valid_to
                )
                for row in certificates
            ],
            posting_date=on,
            amount=base,
            ytd_amount=ytd_amount,
            ytd_withheld_base=ytd_base,
            certificate_consumed=consumed,
            precision=facts.amount_precision,
            rounding=facts.rounding_mode,
        )
    except (ConflictError, ValidationFailedError) as exc:
        outcome.fail("WITHHOLDING_UNRESOLVED", exc.message)
        return None
    return section, result


async def _finish(
    db: AsyncSession,
    access: Access,
    outcome: Outcome,
    user: list[JournalLineCreate],
    postings: list[Posting],
    registration_id: str | None,
) -> list[dict[str, Any]]:
    """Resolve postings to accounts, merge them and append them after the caller's lines."""
    cache: dict[str, uuid.UUID | None] = {}
    effects: list[tuple[uuid.UUID, Side, Decimal]] = []
    labels: dict[tuple[uuid.UUID, Side], str] = {}
    for posting in postings:
        account = posting.account_id
        if posting.purpose is not None:
            scoped = None if posting.purpose.startswith(("TDS_", "TCS_")) else registration_id
            account = await _mapping(
                db, access, posting.purpose, scoped, outcome.posting_date, cache
            )
            if account is None:
                outcome.fail(
                    "MAPPING_MISSING", f"no single effective {posting.purpose} posting mapping"
                )
                continue
        assert account is not None
        labels.setdefault((account, posting.side), posting.purpose or "GST_NOT_RECOVERABLE")
        effects.append((account, posting.side, posting.amount))
    generated = rules.aggregate(effects)
    outcome.lines = [*user]
    outcome.purposes = [None] * len(user)
    outcome.line_count = len(user)
    rendered = []
    for account, side, amount in generated:
        label = labels[(account, side)]
        outcome.lines.append(_line(account, side, outcome.currency, amount, label))
        outcome.purposes.append(label)
        rendered.append(
            {
                "sequence": len(outcome.lines),
                "account_id": str(account),
                "side": side,
                "amount": str(amount),
                "purpose": label,
            }
        )
    if len(outcome.lines) > 200:
        outcome.fail("LINE_LIMIT", "the voucher would exceed 200 journal lines")
    elif not outcome.exceptions and rules.balance(
        (line.side, line.amount) for line in outcome.lines
    ):
        outcome.fail("UNBALANCED", "the voucher does not balance after tax")
    return rendered


def _seal(
    outcome: Outcome,
    request: dict[str, Any],
    gst: _Gst | None,
    party: _Party,
    withheld: tuple[m.WithholdingSection, WithholdingResult] | None,
    withholding_amount: Decimal | None,
    rendered: list[dict[str, Any]],
) -> None:
    computation = gst.computation if gst else None
    determination = gst.determination if gst else None
    company = gst.company if gst else None
    certificate_base = None
    section, result = withheld if withheld else (None, None)
    if result is not None and result.certificate_id is not None:
        certificate_base = sum(
            (p.base_amount for p in result.portions if p.rate_source == "CERTIFICATE"), ZERO
        )
    registration_id = (
        uuid.UUID(str(company.registration["id"])) if company and company.registration else None
    )
    place: str | None = None
    if gst and determination:
        fallback = party.state if outcome.direction == "SALE" else company and company.state
        place = rules.bare_state(gst_place(request)) or fallback or None
    withholding = (
        None
        if section is None or result is None
        else {
            "kind": section.kind,
            "section_id": str(section.id),
            "amount": str(withholding_amount),
            "applies": result.applies,
            "reason": result.reason,
            "profile_id": str(result.profile_id),
            "rate_id": str(result.rate_id) if result.rate_id else None,
            "certificate_id": str(result.certificate_id) if result.certificate_id else None,
            "threshold_crossed": result.threshold_crossed,
            "base_amount": str(result.base_amount),
            "withholding_amount": str(result.withholding_amount),
            "portions": [
                {
                    "base_amount": str(p.base_amount),
                    "rate_percent": str(p.rate_percent),
                    "rate_source": p.rate_source,
                    "amount": str(p.amount),
                }
                for p in result.portions
            ],
        }
    )
    outcome.snapshot = {
        "version": rules.SNAPSHOT_VERSION,
        "kind": outcome.kind,
        "direction": outcome.direction,
        "posting_date": outcome.posting_date.isoformat(),
        "currency": outcome.currency,
        "company_registration_id": str(registration_id) if registration_id else None,
        "company_regime": company.regime if company else None,
        "party_id": str(party.party_id) if party.party_id else None,
        "party_registration_id": str(party.registration_id) if party.registration_id else None,
        "party_type": party.type,
        "party_state": party.state,
        "place_of_supply": place,
        "reverse_charge": bool(gst and gst.reverse_charge),
        "lines": gst.evidence if gst else [],
        "computation": computation.snapshot() if computation else None,
        "withholding": withholding,
        "postings": rendered,
        "party_amount": None if outcome.party_amount is None else str(outcome.party_amount),
    }
    outcome.values = {
        "direction": outcome.direction,
        "party_id": party.party_id,
        "company_registration_id": registration_id,
        "party_registration_id": party.registration_id,
        "place_of_supply": place,
        "supply_context": determination.context.value if determination else None,
        "supply_reason": determination.reason.value if determination else None,
        "reverse_charge": bool(gst and gst.reverse_charge),
        "currency": outcome.currency,
        "taxable_value": outcome.taxable_value,
        "tax_total": outcome.tax_total,
        "withholding_kind": section.kind if section else None,
        "withholding_section_id": section.id if section else None,
        "withholding_amount": withholding_amount if section else None,
        "withholding_base": result.base_amount if result else None,
        "withholding_tax": result.withholding_amount if result else None,
        "certificate_id": result.certificate_id if result and certificate_base else None,
        "certificate_base": certificate_base if certificate_base else None,
        "line_count": outcome.line_count,
        "request": request,
        "snapshot": outcome.snapshot,
        "snapshot_hash": rules.snapshot_hash(outcome.snapshot),
    }


def charging_id(gst: _Gst | None) -> str | None:
    if gst is None or gst.company is None or gst.company.registration is None:
        return None
    return str(gst.company.registration["id"])


def gst_place(request: dict[str, Any]) -> str | None:
    tax = request.get("tax") or {}
    value = tax.get("place_of_supply")
    return str(value) if value else None


def journal_request(body: JournalCreate) -> dict[str, Any]:
    return body.model_dump(mode="json", exclude={"expected_version"})


def source_request(body: SourceCreate) -> dict[str, Any]:
    """The stored request; untaxed requests keep their pre-Phase-8 shape for replay."""
    return body.model_dump(mode="json", exclude={"tax"} if body.tax is None else None)


async def _scoped_accounts(db: AsyncSession, access: Access, ids: set[uuid.UUID]) -> None:
    """Object scope for every line account, so a preview never runs on another company's."""
    rows = list(await db.scalars(select(m.Account).where(m.Account.id.in_(ids)).limit(201)))
    if any(row.company_id != access.context.company_id for row in rows):
        raise PermissionDeniedError("resource is outside the requested company")
    if len(rows) != len(ids):
        raise NotFoundError("resource not found")


async def resolve_journal(db: AsyncSession, access: Access, body: JournalCreate) -> Outcome:
    tax = cast(VoucherTax, body.tax)
    base = access.context.base_currency
    outcome = Outcome("MANUAL", tax.direction, body.posting_date, base)
    if tax.party_id is not None:
        authorize(access, BY_NAME["party"], "read")
        await company_object(db, m.Party, tax.party_id, company_id=access.context.company_id)
    await _scoped_accounts(db, access, {line.account_id for line in body.lines})
    if any(line.currency != base or line.exchange_rate != ONE for line in body.lines):
        outcome.fail("FOREIGN_CURRENCY", "voucher tax is posted in the company base currency")
    side = rules.side_of(tax.direction)
    defaults = await _defaults(
        db,
        access,
        {line.account_id for line in body.lines if line.side == side},
        tax.direction,
        body.posting_date,
    )
    candidates = [
        (index, line.account_id, line.amount)
        for index, line in enumerate(body.lines, 1)
        if line.side == side and line.account_id in defaults
    ]
    if not candidates:
        outcome.fail(
            "DEFAULT_MISSING", f"no {side.lower()} line is on an account with a tax default"
        )
    party = await _party(db, access, tax.party_id, tax, body.posting_date, outcome)
    gst: _Gst | None = None
    postings: list[Posting] = []
    if not outcome.exceptions:
        gst = await _gst(db, access, tax, party, outcome, candidates, defaults)
        if gst.computation is not None:
            postings = rules.gst_postings(tax.direction, gst.computation, gst.taxed)
            outcome.taxable_value = gst.computation.totals.taxable_value
            outcome.tax_total = gst.computation.totals.tax_total
    registration = (
        str(gst.company.registration["id"])
        if gst and gst.company and gst.company.registration
        else None
    )
    rendered = await _finish(db, access, outcome, list(body.lines), postings, registration)
    _seal(outcome, journal_request(body), gst, party, None, None, rendered)
    return outcome


async def resolve_source(
    db: AsyncSession,
    access: Access,
    body: SourceCreate,
    account: m.Account,
    offset: m.Account,
) -> Outcome:
    tax = cast(SourceTax, body.tax)
    base = access.context.base_currency
    direction: Direction = "SALE" if body.kind == "INVOICE" else "PURCHASE"
    outcome = Outcome(body.kind, direction, body.posting_date, base)
    if body.currency != base or body.exchange_rate != ONE:
        outcome.fail("FOREIGN_CURRENCY", "voucher tax is posted in the company base currency")
    party_id = cast(uuid.UUID, account.party_id)
    party = await _party(db, access, party_id, tax, body.posting_date, outcome)
    taxable = tax.taxable_value if tax.taxable_value is not None else body.amount
    gst: _Gst | None = None
    postings: list[Posting] = []
    if tax.gst:
        defaults = await _defaults(db, access, {offset.id}, direction, body.posting_date)
        if offset.id not in defaults:
            outcome.fail("DEFAULT_MISSING", "the counterpart account has no tax default", 2)
        elif not outcome.exceptions:
            gst = await _gst(db, access, tax, party, outcome, [(2, offset.id, taxable)], defaults)
            if gst.computation is not None:
                postings = rules.gst_postings(direction, gst.computation, gst.taxed)
                taxable = gst.computation.totals.taxable_value
                outcome.tax_total = gst.computation.totals.tax_total
    outcome.taxable_value = taxable if body.kind != "PAYMENT" else ZERO
    gross = taxable + outcome.tax_total
    withheld = None
    withholding_amount = None
    tds = ZERO
    if tax.withholding_section_id is not None and not outcome.exceptions:
        withholding_amount = rules.withholding_base(body.kind, taxable, gross, body.amount)
        withheld = await _withholding(
            db, access, tax.withholding_section_id, party_id, withholding_amount, outcome
        )
        if withheld is not None:
            section, result = withheld
            outcome.withholding_kind = section.kind
            outcome.withholding_tax = result.withholding_amount
            tds = result.withholding_amount
            if tds:
                postings.append(Posting("CREDIT", tds, purpose=f"{section.kind}_PAYABLE"))
    charged = rules.supplier_tax(gst.computation if gst else None, gst.taxed if gst else [])
    expected = rules.party_amount(body.kind, taxable, charged, outcome.tax_total, tds)
    outcome.party_amount = expected if body.kind != "PAYMENT" else body.amount
    if body.kind != "PAYMENT" and body.amount != expected:
        outcome.fail("PARTY_AMOUNT_MISMATCH", f"the party amount must be {expected} after tax")
    counterpart = taxable if body.kind != "PAYMENT" else body.amount - tds
    debit = (account.party_role == "CUSTOMER") == (body.kind in {"INVOICE", "BILL"})
    user: list[JournalLineCreate] = []
    if counterpart <= ZERO:
        outcome.fail("PARTY_AMOUNT_MISMATCH", "withholding consumes the whole payment")
    else:
        user = [
            _line(account.id, "DEBIT" if debit else "CREDIT", base, body.amount),
            _line(offset.id, "CREDIT" if debit else "DEBIT", base, counterpart),
        ]
    registration = (
        str(gst.company.registration["id"])
        if gst and gst.company and gst.company.registration
        else None
    )
    rendered = await _finish(db, access, outcome, user, postings, registration)
    _seal(outcome, source_request(body), gst, party, withheld, withholding_amount, rendered)
    return outcome


async def preview(db: AsyncSession, access: Access, body: TaxPreviewRequest) -> TaxPreview:
    """Read-only; resolves exactly what drafting would, reporting exceptions instead of failing."""
    from accounting.tasks.journal_drafts import require_preview_fields
    from accounting.tasks.party_documents import party_account

    authorize(access, BY_NAME["account_tax_default"], "read")
    require_preview_fields(access)
    financial_context(access)
    if body.journal is not None:
        outcome = await resolve_journal(db, access, body.journal)
    else:
        source = cast(SourceCreate, body.source_document)
        account = await party_account(db, access, source.account_id)
        offset = await company_object(
            db, m.Account, source.counterpart_account_id, company_id=access.context.company_id
        )
        if offset.kind == "PARTY":
            raise ValidationFailedError("counterpart must be a non-party account")
        outcome = await resolve_source(db, access, source, account, offset)
    return TaxPreview(
        status="READY" if outcome.ready else "EXCEPTION",
        exceptions=[
            TaxExceptionItem(code=item.code, message=item.message, line=item.line)
            for item in outcome.exceptions
        ],
        posting_date=outcome.posting_date,
        direction=outcome.direction,
        currency=outcome.currency,
        taxable_value=outcome.taxable_value,
        tax_total=outcome.tax_total,
        withholding_kind=cast(Literal["TDS", "TCS"] | None, outcome.withholding_kind),
        withholding_tax=outcome.withholding_tax,
        party_amount=outcome.party_amount,
        analysis=outcome.snapshot if outcome.ready else None,
        lines=[
            TaxPreviewLine(
                sequence=index,
                account_id=line.account_id,
                side=line.side,
                currency=line.currency,
                amount=line.amount,
                generated=index > outcome.line_count,
                purpose=purpose,
            )
            for index, (line, purpose) in enumerate(
                zip(outcome.lines, outcome.purposes, strict=True), 1
            )
        ],
    )


async def stored(db: AsyncSession, journal: Journal) -> JournalTax | None:
    row: JournalTax | None = await db.scalar(
        select(JournalTax).where(
            JournalTax.company_id == journal.company_id, JournalTax.journal_id == journal.id
        )
    )
    return row


def generated_accounts(
    row: JournalTax | None, lines: Sequence[JournalLine]
) -> frozenset[uuid.UUID]:
    """Accounts that appear only on generated tax lines (exempt from the manual policy)."""
    if row is None:
        return frozenset()
    entered = {line.account_id for line in lines[: row.line_count]}
    return frozenset(line.account_id for line in lines[row.line_count :]) - entered


async def verify(db: AsyncSession, access: Access, journal: Journal) -> None:
    """Re-derive the stored analysis at posting; any difference refuses the post."""
    row = await stored(db, journal)
    if row is None:
        return
    require_fields(access, "journal_tax", {"line_count", "request", "snapshot_hash"}, row=row)
    if journal.kind == "MANUAL":
        outcome = await resolve_journal(db, access, JournalCreate.model_validate(row.request))
    else:
        from accounting.tasks.party_documents import party_account

        body = SourceCreate.model_validate(row.request)
        account = await party_account(db, access, body.account_id)
        offset = await company_object(
            db, m.Account, body.counterpart_account_id, company_id=journal.company_id
        )
        outcome = await resolve_source(db, access, body, account, offset)
    outcome.require_ready()
    from accounting.tasks.journal_drafts import line_input, lines

    current = [line_input(line) for line in await lines(db, journal.company_id, journal.id)]
    if (
        outcome.values["snapshot_hash"] != row.snapshot_hash
        or outcome.line_count != row.line_count
        or [line.model_dump() for line in outcome.lines] != [line.model_dump() for line in current]
    ):
        raise ConflictError("tax analysis changed; recalculate the draft")
