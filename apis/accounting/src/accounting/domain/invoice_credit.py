"""Amount-level input-credit history; recording a purchase never grants a tax claim.

This is the ordinary, current India profile. The owner resolves authoritative
evidence and serializes writes before applying these pure transition rules.
Exceptional historical relief and imports require separate dated profiles.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_calculation import exact, money


@dataclass(frozen=True)
class CreditEvidence:
    document_verified: bool
    supply_received: bool
    business_use: bool
    restrictions_checked: bool
    supplier_report_matched: bool
    tax_payment_verified: bool
    return_filed: bool
    supplier_paid: bool
    reference: str


@dataclass(frozen=True)
class CreditTerms:
    supplier_invoice_date: dt.date
    reverse_charge: bool
    recoverable: bool
    annual_return_filed_on: dt.date | None = None


@dataclass(frozen=True)
class CreditEvent:
    kind: str
    amount: Decimal
    event_date: dt.date
    evidence: CreditEvidence | None = None


@dataclass(frozen=True)
class CreditPosition:
    recorded: Decimal
    pending: Decimal
    eligible_unclaimed: Decimal
    claimed: Decimal
    suspended: Decimal
    blocked: Decimal
    rcm_discharged: Decimal


def credit_deadline(terms: CreditTerms) -> dt.date:
    # Statutory GST FY is April-March even where the company's GL year differs.
    year = terms.supplier_invoice_date.year - (terms.supplier_invoice_date.month < 4)
    if year < 2025 or year >= 9999:
        raise ValidationFailedError(
            "input credit requires a supported current statutory-year profile"
        )
    november = dt.date(year + 1, 11, 30)
    annual = terms.annual_return_filed_on
    return min(november, annual) if annual else november


def verify_evidence(
    event: CreditEvent, terms: CreditTerms, *, claiming: bool, reclaim: bool = False
) -> None:
    proof = event.evidence
    if proof is None or not proof.reference.strip() or len(proof.reference) > 500:
        raise ValidationFailedError("credit transition requires retained verification evidence")
    if not all(
        (
            proof.document_verified,
            proof.supply_received,
            proof.business_use,
            proof.restrictions_checked,
            proof.tax_payment_verified,
        )
    ):
        raise ValidationFailedError("input-credit conditions have not been verified")
    if not terms.reverse_charge and not proof.supplier_report_matched:
        raise ValidationFailedError("forward-charge credit requires supplier-report evidence")
    if claiming and not proof.return_filed:
        raise ValidationFailedError("claimed credit requires the acknowledged return evidence")
    if reclaim and not proof.supplier_paid:
        raise ValidationFailedError("payment-related reclaim requires settlement evidence")
    if event.event_date < terms.supplier_invoice_date:
        raise ValidationFailedError("credit evidence precedes its supplier document")
    if not reclaim and (
        event.event_date > credit_deadline(terms)
        or (
            terms.annual_return_filed_on is not None
            and event.event_date >= terms.annual_return_filed_on
        )
    ):
        raise ValidationFailedError("ordinary input-credit time limit has expired")
    # Forward-charge credit after 180 days requires settlement or the applicable
    # reversal/reclaim workflow. A bank deposit is not evidence of RCM discharge.
    if (
        not terms.reverse_charge
        and (event.event_date - terms.supplier_invoice_date).days > 180
        and not proof.supplier_paid
    ):
        raise ValidationFailedError("unpaid supplier consideration requires credit reversal")


def position(terms: CreditTerms, events: tuple[CreditEvent, ...]) -> CreditPosition:
    credit_deadline(terms)
    recorded = eligible = claimed = suspended = blocked = paid = Fraction()
    last_date: dt.date | None = None
    if not events or len(events) > 1000:
        raise ValidationFailedError("credit history requires a bounded recorded source")
    for sequence, event in enumerate(events):
        amount = exact(event.amount)
        if amount <= 0 or (last_date is not None and event.event_date < last_date):
            raise ValidationFailedError("credit events require positive amounts and ordered dates")
        if event.event_date < terms.supplier_invoice_date:
            raise ValidationFailedError("credit event precedes its supplier document")
        last_date = event.event_date
        if sequence == 0:
            if event.kind != "RECORD":
                raise ValidationFailedError(
                    "credit history must begin with the recorded purchase tax"
                )
            recorded = amount
            if not terms.recoverable:
                blocked = amount
            continue
        if event.kind == "VERIFY":
            verify_evidence(event, terms, claiming=False)
            if not terms.recoverable or amount > recorded - blocked - eligible:
                raise ValidationFailedError("verification exceeds the pending recoverable amount")
            if terms.reverse_charge and eligible + amount > paid:
                raise ValidationFailedError("RCM credit requires prior statutory cash discharge")
            eligible += amount
        elif event.kind == "CLAIM":
            verify_evidence(event, terms, claiming=True)
            if amount > eligible - claimed - suspended:
                raise ValidationFailedError("claim exceeds verified unclaimed credit")
            claimed += amount
        elif event.kind == "REVERSE_PAYMENT":
            if terms.reverse_charge or amount > claimed:
                raise ValidationFailedError(
                    "payment-related reversal exceeds claimed forward-charge credit"
                )
            if (
                (event.event_date - terms.supplier_invoice_date).days <= 180
                or event.evidence is None
                or event.evidence.supplier_paid
                or not event.evidence.reference.strip()
            ):
                raise ValidationFailedError(
                    "payment-related reversal requires overdue unpaid consideration evidence"
                )
            claimed -= amount
            suspended += amount
        elif event.kind == "RECLAIM_PAYMENT":
            verify_evidence(event, terms, claiming=True, reclaim=True)
            if terms.reverse_charge or amount > suspended:
                raise ValidationFailedError("reclaim exceeds payment-related reversed credit")
            suspended -= amount
            claimed += amount
        elif event.kind == "BLOCK":
            if amount > recorded - blocked - eligible:
                raise ValidationFailedError("blocked amount exceeds unverified credit")
            blocked += amount
        elif event.kind == "RCM_DISCHARGE":
            if not terms.reverse_charge or amount > recorded - paid:
                raise ValidationFailedError("RCM discharge exceeds recorded reverse-charge tax")
            if (
                event.evidence is None
                or not event.evidence.reference.strip()
                or not event.evidence.tax_payment_verified
            ):
                raise ValidationFailedError("RCM discharge requires statutory cash-offset evidence")
            paid += amount
        else:
            raise ValidationFailedError("unsupported or duplicate credit event")
    return CreditPosition(
        *(
            money(value, 4)
            for value in (
                recorded,
                recorded - blocked - eligible,
                eligible - claimed - suspended,
                claimed,
                suspended,
                blocked,
                paid,
            )
        )
    )
