"""Resolving what a company was registered and licensed as on a date.

docs/company.md §2.3 and §4.4. Both tax registration and licences gate posting,
both resolve by the document's **``posting_date``**, and both must be readable by
the service doing the writing without a synchronous call into ``identity`` inside
a money transaction (CLAUDE.md invariant 7). So the resolution lives here, beside
``assert_postable``, and every service reads it from its own replica.

Three rules do the work, and each one is a refusal to guess.

**Resolution is by ``posting_date``, never ``now()`` and never ``created_at``**
(CLAUDE.md invariant 4). A distributor on Composition until 30 September and
Regular from 1 October, reprinting an invoice dated 20 August in November, must
see Composition — the regime the return already reported.

**A gap returns ``None``.** A company genuinely may be unregistered for a stretch,
and falling back to the nearest row would put a GSTIN on an invoice issued when
the company held none. The caller decides what an unregistered posting means; this
module will not decide it by picking the closest thing.

**An ambiguous answer raises rather than picks.** Overlapping validity is rejected
at write time, so two matches mean the write path was bypassed — and choosing one
by row order would make the tax on a document depend on the query plan.

No ORM here (CLAUDE.md §4): callers pass plain value objects built from their own
replica rows, which is what lets all of this be tested with no database.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.jurisdiction import gate_kinds
from billing_platform.tax import registration_class as _registration_class


@dataclass(frozen=True, slots=True)
class TaxRegistration:
    """One ``company_tax_registration`` row, reduced to what resolution reads."""

    tax_system: str
    regime: str
    number: str
    jurisdiction_code: str
    valid_from: dt.date
    #: ``None`` is open-ended, not unknown.
    valid_to: dt.date | None = None
    is_primary: bool = False
    #: Prints as registered where it differs from ``company.legal_name``.
    legal_name_on_registration: str | None = None

    @property
    def registration_class(self) -> str:
        """``billing_platform.tax.REGISTRATION_CLASSES`` key, derived from the regime.

        Derived rather than stored so it can never disagree with the regime it
        describes.
        """
        return _registration_class(self.tax_system, self.regime)


@dataclass(frozen=True, slots=True)
class Licence:
    """One ``company_licence`` row, reduced to what the posting gate reads."""

    kind: str
    number: str
    valid_from: dt.date
    valid_to: dt.date | None = None
    is_primary: bool = False
    premises_address_id: uuid.UUID | None = None


def covers(valid_from: dt.date, valid_to: dt.date | None, on: dt.date) -> bool:
    """Whether a validity window includes ``on``.

    Inclusive at both ends. A licence expiring on the 31st is valid on the 31st —
    the certificate says so, and an exclusive bound would reject a day's legitimate
    trading.
    """
    return valid_from <= on and (valid_to is None or on <= valid_to)


def assert_window_ordered(
    valid_from: dt.date, valid_to: dt.date | None, *, what: str = "record"
) -> None:
    """Reject a validity window that ends before it starts.

    A backwards window is not merely wrong, it is invisible: ``covers`` returns
    ``False`` for every date, so the row resolves for nothing and reads as a gap.
    The document is then refused, or issued without a registration number, with no
    hint that a row exists at all.
    """
    if valid_to is not None and valid_to < valid_from:
        raise ValidationFailedError(
            f"this {what} ends on {valid_to.isoformat()}, before it starts on "
            f"{valid_from.isoformat()}.",
            fields={"valid_to": "earlier than valid_from"},
        )


def registrations_valid_on(
    registrations: Iterable[TaxRegistration],
    *,
    posting_date: dt.date,
    jurisdiction_code: str | None = None,
    tax_system: str | None = None,
    registration_class: str | None = None,
) -> tuple[TaxRegistration, ...]:
    """Every registration in force on ``posting_date``, narrowed by the filters given."""
    return tuple(
        registration
        for registration in registrations
        if covers(registration.valid_from, registration.valid_to, posting_date)
        and (jurisdiction_code is None or registration.jurisdiction_code == jurisdiction_code)
        and (tax_system is None or registration.tax_system == tax_system)
        and (registration_class is None or registration.registration_class == registration_class)
    )


def resolve_tax_registration(
    registrations: Iterable[TaxRegistration],
    *,
    jurisdiction_code: str,
    posting_date: dt.date,
    tax_system: str | None = None,
    registration_class: str | None = None,
) -> TaxRegistration | None:
    """The registration a document falls under, or ``None`` for a genuine gap.

    ``tax_system`` and ``registration_class`` are optional because a jurisdiction
    normally holds one registration, and required in practice wherever a company
    holds two: overlap is only rejected *within* a ``(tax_system,
    registration_class, jurisdiction_code)`` group, so a regular GSTIN and a
    TDS-deductor registration may legally be in force in the same state at the same
    time. A posting that charges tax asks for ``registration_class="supplier"``.
    Left unspecified with two matches, this raises rather than choosing.

    Takes the company's rows rather than a ``company_id``: the caller has already
    loaded them under its own tenant filter, and a helper here that issued its own
    query would be a second data path with no tenant scope of its own.
    """
    matches = registrations_valid_on(
        registrations,
        posting_date=posting_date,
        jurisdiction_code=jurisdiction_code,
        tax_system=tax_system,
        registration_class=registration_class,
    )

    if not matches:
        # Deliberately not the nearest row, and deliberately not an error.
        return None

    if len(matches) > 1:
        found = ", ".join(sorted(f"{m.tax_system}/{m.number}" for m in matches))
        raise ConflictError(
            f"more than one tax registration is valid in {jurisdiction_code} on "
            f"{posting_date.isoformat()}: {found}. Resolution must not depend on row order.",
        )

    return matches[0]


def assert_no_overlap(registrations: Sequence[TaxRegistration]) -> None:
    """Reject overlapping validity within a ``(tax_system, registration_class,
    jurisdiction_code)`` group.

    Called on the write path with the rows that *would* exist. Enforced here rather
    than by a constraint because no database can express "no two rows with
    intersecting date ranges" — the unique key on ``valid_from`` stops an exact
    duplicate and nothing else.

    Overlap between *different* tax systems, or between different registration
    classes of one system, in one jurisdiction is legitimate and left alone: an
    Indian company can hold a regular GSTIN and a TDS-deductor (or ISD) registration
    for the same state simultaneously. Regular and composition are the same class
    (``supplier``), so a regime change is still one timeline that must not overlap.
    """
    grouped: dict[tuple[str, str, str], list[TaxRegistration]] = {}
    for registration in registrations:
        key = (
            registration.tax_system,
            registration.registration_class,
            registration.jurisdiction_code,
        )
        grouped.setdefault(key, []).append(registration)

    for (tax_system, _, jurisdiction_code), group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda registration: registration.valid_from)
        for earlier, later in pairwise(ordered):
            if earlier.valid_to is None or later.valid_from <= earlier.valid_to:
                ends = "open-ended" if earlier.valid_to is None else earlier.valid_to.isoformat()
                raise ConflictError(
                    f"{tax_system} registrations in {jurisdiction_code} overlap: "
                    f"{earlier.number} from {earlier.valid_from.isoformat()} to {ends}, "
                    f"and {later.number} from {later.valid_from.isoformat()}. "
                    "Close the earlier one the day before the later one starts.",
                )


def licences_valid_on(
    licences: Iterable[Licence],
    *,
    posting_date: dt.date,
    kinds: Iterable[str] | None = None,
) -> tuple[Licence, ...]:
    """Every licence in force on ``posting_date``, optionally narrowed to ``kinds``."""
    wanted = None if kinds is None else frozenset(kinds)
    return tuple(
        licence
        for licence in licences
        if covers(licence.valid_from, licence.valid_to, posting_date)
        and (wanted is None or licence.kind in wanted)
    )


def resolve_licence(
    licences: Iterable[Licence],
    *,
    kind: str,
    posting_date: dt.date,
    premises_address_id: uuid.UUID | None = None,
) -> Licence | None:
    """The licence of one kind to print on a document, or ``None``.

    Several may be valid at once — a licence is usually per premises — so unlike a
    tax registration this is not ambiguous, it is a choice: the primary one, and
    otherwise the most recently issued. Both clients and the print template need a
    single answer, and it must be the same answer every time the document is
    reprinted, which is why ``valid_from`` breaks the tie rather than row order.
    When a premises is supplied, only licences for that exact address are ranked.
    """
    matches = licences_valid_on(licences, posting_date=posting_date, kinds=(kind,))
    if premises_address_id is not None:
        matches = tuple(
            licence for licence in matches if licence.premises_address_id == premises_address_id
        )
    if not matches:
        return None
    return max(
        matches, key=lambda licence: (licence.is_primary, licence.valid_from, licence.number)
    )


def assert_company_can_issue(
    licences: Iterable[Licence],
    *,
    country_code: str,
    posting_date: dt.date,
    line_gates: Iterable[str],
    operation: str | None = None,
    premises_address_id: uuid.UUID | None = None,
    drug_class: str | None = None,
    drug_classes: Iterable[str] = (),
) -> None:
    """Refuse a document whose lines need a licence the company does not hold.

    ``line_gates`` is the set of gates the document's items carry. For an India
    scheduled-drug line, callers must supply every reviewed drug class present
    on the document, the sale operation and licensed premises. ``drug_class``
    covers a single class; ``drug_classes`` covers mixed-class documents. A gate
    with no licence valid on ``posting_date`` **rejects the posting**; it is never
    a warning
    (docs/company.md §4.4). An expiry discovered at the till is a shop that has
    stopped trading, which is what ``renewal_reminder_days`` and the Beat job exist
    to prevent.

    **A gate the jurisdiction profile does not cover fails closed.** If no licence
    kind in the profile declares the gate, the answer is "this platform does not
    know what permits that here", and the safe reading of that is refusal — an
    incomplete profile must not become permission to sell a controlled item
    unlicensed.

    ``document_kind`` is deliberately not a parameter: no document kind exempts the
    gate, and a parameter that is accepted and never read reads as an exemption
    mechanism that does not exist. A delivery challan for a scheduled drug needs
    the licence exactly as much as the invoice does.
    """
    held = licences_valid_on(licences, posting_date=posting_date)

    classes = set(drug_classes)
    if drug_class is not None:
        classes.add(drug_class)
    for gate in sorted(set(line_gates)):
        if gate == "scheduled_drug" and (
            operation not in {"RETAIL", "WHOLESALE"}
            or premises_address_id is None
            or not classes
            or not classes <= {"OTHER_THAN_C_C1_X", "C_C1_EXCLUDING_X"}
        ):
            raise ConflictError(
                "scheduled-drug issue needs a supported drug class, retail/wholesale "
                "operation and premises"
            )
        required_classes: tuple[str | None, ...] = (
            tuple(sorted(classes)) if gate == "scheduled_drug" else (None,)
        )
        for required_class in required_classes:
            permitted_by = gate_kinds(
                country_code, gate, operation=operation, drug_class=required_class
            )
            if not permitted_by:
                raise ConflictError(
                    f"no licence in the {country_code} jurisdiction profile permits {gate!r}, "
                    "so this document cannot be issued here.",
                )
            eligible = (
                (licence for licence in held if licence.premises_address_id == premises_address_id)
                if gate == "scheduled_drug"
                else iter(held)
            )
            if not any(licence.kind in permitted_by for licence in eligible):
                raise ConflictError(
                    f"a line requires {gate!r} ({required_class or 'general'}) but no "
                    f"{' or '.join(permitted_by)} licence is valid on {posting_date.isoformat()}.",
                )
