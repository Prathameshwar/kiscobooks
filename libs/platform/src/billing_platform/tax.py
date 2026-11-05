"""The tax-system and regime catalogues — code, not data.

``tax_system`` answers "which tax framework does this entity operate under", and
it effectively never changes: an Indian GST company does not become a UK VAT
entity (docs/company.md §2). The *regime* inside a system does change, mid-year
and routinely, which is why the two are separate axes and why regimes are stored
on ``company_tax_registration`` with validity dates rather than as a current-value
column on ``company``.

Here in ``libs/platform`` for the same reason the ISO tables are: every service
stores a ``tax_system`` value on a replica, and a value one service accepts and
another rejects is a posting that cannot be reproduced. A tenant cannot invent
one, because a tax system is a claim that code exists to compute it.

**Regime decides whether tax may be charged at all**, so it is a code catalogue
for the same reason permissions are (docs/company.md §2.3): a composition dealer
must not charge GST on an invoice, and that rule can only be checked statically
against a fixed set of values. What lives here is the catalogue and the two
properties every service reads off it; *which* regime a document falls under is
resolved from the registration valid on its ``posting_date``
(``billing_platform.statutory``).

Both catalogues are validated at **import time**, so a malformed entry fails the
boot rather than the first request that touches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from billing_platform.errors import ValidationFailedError

#: docs/company.md §2.1. Keys are immutable once shipped — they appear in stored
#: rows, in replicas, and in filed statutory output.
TAX_SYSTEMS: Final[dict[str, str]] = {
    "gst_in": "India GST",
    "vat_gb": "UK VAT",
    "vat_eu": "EU VAT",
    "vat_ae": "UAE VAT",
    "vat_sa": "Saudi VAT",
    "gst_au": "Australia GST",
    "gst_ca": "Canada GST/HST/PST",
    "sales_tax_us": "US state & local sales tax",
    #: A real value, not a null: "not registered for indirect tax" is a posture a
    #: company holds deliberately, and a NULL would be indistinguishable from
    #: "nobody has filled this in yet".
    "none": "No indirect tax registration",
}


def assert_known_tax_system(tax_system: str) -> None:
    """Reject a tax system outside the catalogue.

    Raised as a 422 rather than silently stored: an unknown value would flow into
    every replica and be discovered by whichever service first tried to compute
    tax from it.
    """
    if tax_system not in TAX_SYSTEMS:
        raise ValidationFailedError(
            f"unknown tax system: {tax_system!r}",
            fields={"tax_system": "not in the platform catalogue"},
        )


#: What a registration *is for*, independent of how tax on it is computed.
#:
#: Overlap is only meaningful between registrations that compete to answer the same
#: question. A company's regular GSTIN and its GST TDS-deductor registration in the
#: same state are both ``gst_in`` and both in force at once, legitimately: one is the
#: supplier identity printed on invoices, the other exists only to deduct. Grouping
#: them together rejected a real company's paperwork; grouping by class keeps
#: "composition until 30 September, regular from 1 October" as one timeline (both
#: ``supplier``) while letting the deductor registration run beside it.
#:
#: Keys are immutable once shipped. A new class is a statement that two
#: registrations of different classes may coexist, so it is a reviewed code change.
REGISTRATION_CLASSES: Final[dict[str, str]] = {
    "supplier": "Makes outward supplies under this registration",
    "isd": "Input Service Distributor; distributes credit, makes no supply",
    "tds_deductor": "Registered only to deduct tax at source",
    "tcs_collector": "E-commerce operator registered to collect tax at source",
}

#: The class a regime belongs to unless it says otherwise — and the class an
#: uncatalogued pairing falls back to, because it groups with the most rows and so
#: produces the most overlap rejections rather than the fewest.
DEFAULT_REGISTRATION_CLASS: Final = "supplier"


@dataclass(frozen=True, slots=True)
class Regime:
    """One entry in a tax system's regime catalogue.

    ``may_charge_tax`` and ``tax_due_on_payment`` change what a posting *computes*,
    which is the test for belonging here. ``registration_class`` changes which other
    registrations this one may coexist with (``REGISTRATION_CLASSES``). Anything
    that only changes what a return looks like belongs to whichever service files it.
    """

    label: str
    #: ``False`` when the regime forbids charging indirect tax on the invoice at
    #: all. A composition dealer who charges GST has issued an illegal document,
    #: so this is a hard refusal in ``domain/``, never a warning.
    may_charge_tax: bool = True
    #: ``True`` when the liability arises on payment rather than on the invoice
    #: date. It moves the amount into a different return period, so the posting
    #: path has to know.
    tax_due_on_payment: bool = False
    #: A key of ``REGISTRATION_CLASSES``; validated at import.
    registration_class: str = DEFAULT_REGISTRATION_CLASS


def _vat_regimes() -> dict[str, Regime]:
    """docs/company.md §2.2's shared set, for the four VAT systems.

    A function rather than one module-level dict reused four times, so each system
    owns its own object: a later amendment to one country's regimes cannot silently
    appear in the other three.
    """
    return {
        "standard": Regime("Normal accrual VAT"),
        "flat_rate": Regime("Fixed percentage; restricted input reclaim"),
        "cash_accounting": Regime("VAT due on payment, not invoice date", tax_due_on_payment=True),
        "annual_accounting": Regime("Annual return with instalments"),
        "margin_scheme": Regime("Second-hand goods"),
        "exempt": Regime("Exempt supplies", may_charge_tax=False),
        "not_registered": Regime("Below threshold or deregistered", may_charge_tax=False),
    }


#: docs/company.md §2.2, keyed by tax system. Regime keys are immutable once
#: shipped: they are stored on ``company_tax_registration`` and reproduced on
#: reprints of filed documents.
#:
#: **A system absent from this mapping accepts no registration.** ``gst_au``,
#: ``gst_ca`` and ``none`` are deliberately absent: their regimes are not
#: documented, and inventing statutory values that then become immutable is worse
#: than refusing until someone writes them down. ``none`` needs none by
#: construction — "not registered" is the *absence* of a registration row, which
#: is exactly what resolution returning ``None`` means.
REGIMES: Final[dict[str, dict[str, Regime]]] = {
    "gst_in": {
        "regular": Regime("Normal registered dealer"),
        "composition": Regime("Flat rate on turnover", may_charge_tax=False),
        "unregistered": Regime("Below threshold", may_charge_tax=False),
        #: Zero-rated, not untaxed: the line still carries a rate, at 0%.
        "sez_unit": Regime("SEZ unit; zero-rated supplies"),
        "sez_developer": Regime("SEZ developer; zero-rated supplies"),
        #: An e-commerce operator's TCS registration runs beside its supplier GSTIN.
        #: Its GSTIN carries a literal ``C`` (``billing_platform.jurisdiction``).
        "ecommerce_operator": Regime(
            "TCS collection obligations", registration_class="tcs_collector"
        ),
        #: An ISD distributes input credit and makes no outward taxable supply.
        "isd": Regime("Input Service Distributor", may_charge_tax=False, registration_class="isd"),
        "casual_taxable_person": Regime("Time-bound registration"),
        #: A TDS deductor registration exists to deduct, not to collect output tax.
        #: Its GSTIN may be TAN-based (``billing_platform.jurisdiction.validate_gstin``).
        "tds_deductor": Regime(
            "GST TDS deductor", may_charge_tax=False, registration_class="tds_deductor"
        ),
    },
    "vat_gb": _vat_regimes(),
    "vat_eu": _vat_regimes(),
    "vat_ae": _vat_regimes(),
    "vat_sa": _vat_regimes(),
    "sales_tax_us": {
        "destination_based": Regime("Rate of the ship-to jurisdiction"),
        "origin_based": Regime("Rate of the ship-from jurisdiction"),
        "exempt_reseller": Regime("Resale exemption certificate held", may_charge_tax=False),
        "not_registered": Regime("No nexus in the jurisdiction", may_charge_tax=False),
    },
}


def regimes_for(tax_system: str) -> dict[str, Regime]:
    """The regime catalogue of one tax system, or a 422.

    A known system with no catalogue is rejected the same way an unknown one is,
    and says so: a registration stored under it would have a ``regime`` value no
    posting path could interpret.
    """
    assert_known_tax_system(tax_system)
    try:
        return dict(REGIMES[tax_system])
    except KeyError:
        raise ValidationFailedError(
            f"{tax_system} has no regime catalogue yet, so it accepts no registration.",
            fields={"tax_system": "no regime catalogue defined for this system"},
        ) from None


def get_regime(tax_system: str, regime: str) -> Regime:
    """The catalogue entry for one ``(tax_system, regime)`` pair, or a 422."""
    known = regimes_for(tax_system)
    try:
        return known[regime]
    except KeyError:
        raise ValidationFailedError(
            f"unknown regime {regime!r} for {tax_system}: expected one of "
            f"{', '.join(sorted(known))}",
            fields={"regime": f"not a {tax_system} regime"},
        ) from None


def may_charge_tax(tax_system: str, regime: str) -> bool:
    """Whether a document under this registration may carry indirect tax.

    Read on the posting path, against the registration resolved for the document's
    ``posting_date`` — never against the company's current regime, or a reprint of
    a filed invoice would show tax the return never reported.
    """
    return get_regime(tax_system, regime).may_charge_tax


def registration_class(tax_system: str, regime: str) -> str:
    """The class of one ``(tax_system, regime)`` pair, never raising.

    Lenient on purpose: it is read on resolution and overlap paths over rows that
    were validated when written. An uncatalogued pairing answers
    ``DEFAULT_REGISTRATION_CLASS``, which groups it with every supplier registration
    — the answer that rejects more, not less. Validation of the pair itself is
    ``get_regime``'s job, on the write path.
    """
    entry = REGIMES.get(tax_system, {}).get(regime)
    return DEFAULT_REGISTRATION_CLASS if entry is None else entry.registration_class


def _validate_catalogues() -> None:
    """Boot check. Four ways an entry can be wrong, all silent at runtime.

    A regime under an unknown system would be unreachable; an empty catalogue
    would make every registration under that system fail at the boundary with a
    confusing message; and a key that is not a lowercase code would be stored and
    then compared against a literal that does not match it; and an unknown
    registration class would put a registration in a group of its own, exempt from
    every overlap check.
    """
    for system, regimes in REGIMES.items():
        if system not in TAX_SYSTEMS:
            raise ValueError(f"regime catalogue names unknown tax system {system!r}")
        if not regimes:
            raise ValueError(f"{system} has an empty regime catalogue; omit the key instead")
        for key, regime in regimes.items():
            if not key.replace("_", "").isalnum() or key != key.lower():
                raise ValueError(f"{system} regime {key!r} is not a lowercase snake_case code")
            if not regime.label:
                raise ValueError(f"{system} regime {key!r} has no label")
            if regime.registration_class not in REGISTRATION_CLASSES:
                raise ValueError(
                    f"{system} regime {key!r} names unknown registration class "
                    f"{regime.registration_class!r}"
                )


_validate_catalogues()
