"""Jurisdiction profiles — what a country's paperwork looks like, as code.

docs/company.md §3. The alternative is columns per country, and it does not
survive the second country: a `pan` column, a `utr` column, an `fssai_number`
column, each NULL for everyone else, each needing a migration to add. So the
*shape* of a jurisdiction is a code-defined profile and the *values* are rows in
``company_statutory_id`` and ``company_licence``.

What that buys, and each of these is the reason for a design choice below:

- The company creation form generates itself from the selected country, so there
  is no per-country branching in either client.
- A validation pattern is reviewable in a diff rather than typed by an admin.
- A new country is one profile entry plus tests, never a migration.

Here in ``libs/platform`` at the same tier as the ISO tables: ``billing`` decides
whether an invoice may be posted, and it needs the licence gates and the
statutory-ID rules locally to do it, without a synchronous call into ``identity``
inside a money transaction (CLAUDE.md invariant 7).

``kind`` values are immutable once shipped — they appear in stored rows.

**Only the two documented profiles are here.** Adding a third means writing its
statutory identifiers and their patterns down, which is a research task with a
reviewer, not a guess: a wrong pattern rejects a valid identifier at the boundary
and a missing licence kind fails a posting gate open.

The catalogue is validated at **import time**, so a malformed profile fails the
boot rather than the first request that reads it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from billing_platform.constants import MONEY_MAX, MONEY_SCALE
from billing_platform.errors import ValidationFailedError
from billing_platform.features import FEATURES
from billing_platform.tax import DEFAULT_REGISTRATION_CLASS, REGISTRATION_CLASSES, TAX_SYSTEMS

#: How a tax registration is scoped in a jurisdiction. India issues one GSTIN per
#: state; the UK issues one VAT number for the country. It decides what
#: ``company_tax_registration.jurisdiction_code`` must hold.
REGISTRATION_SCOPES: Final[frozenset[str]] = frozenset({"state", "country"})


@dataclass(frozen=True, slots=True)
class TaxSystemSpec:
    """One tax system a company in this jurisdiction may register under."""

    tax_system: str
    #: Anchored regex for ``company_tax_registration.number``, or ``None`` where no
    #: single stable format exists. A GSTIN has one; a UK VAT number has several
    #: legitimate shapes (standard, branch, government department, health
    #: authority), and a pattern covering only the common one would reject valid
    #: registrations at the boundary — worse than not checking.
    number_pattern: str | None = None
    #: Further anchored shapes accepted **only** for a registration of one class
    #: (``billing_platform.tax.REGISTRATION_CLASSES``), as ``(class, pattern)``
    #: pairs. Accepted in addition to ``number_pattern``, never instead of it.
    class_number_patterns: tuple[tuple[str, str], ...] = ()
    #: The last character is a GSTIN-style mod-36 check character over the rest.
    mod36_check: bool = False
    #: The first two characters are the registration state's
    #: ``state.tax_jurisdiction_code`` (Maharashtra ``27``).
    state_prefixed: bool = False

    def number_patterns_for(self, registration_class: str) -> tuple[str, ...]:
        """Every shape a number of this class may take; empty means unchecked."""
        if self.number_pattern is None:
            return ()
        extra = tuple(p for cls, p in self.class_number_patterns if cls == registration_class)
        return (self.number_pattern, *extra)


@dataclass(frozen=True, slots=True)
class StatutoryIdSpec:
    """One statutory identifier a company in this jurisdiction may hold."""

    kind: str
    label: str
    #: Anchored regex the full value is checked against, or ``None`` where no
    #: stable format exists. Checked *before* a restricted value is discarded.
    pattern: str | None = None
    #: The company cannot be completed without it.
    required: bool = False
    #: Printed on documents, which is why a restricted identifier can never be one.
    prints_on_invoice: bool = False
    #: A personal identity number — AADHAAR, SSN and their equivalents. The full
    #: value is **never stored** (CLAUDE.md §5.10, docs/company.md §4.3): the
    #: platform keeps the last four digits and a verification reference.
    #:
    #: One flag, not the doc's ``sensitivity`` + ``storage`` pair: two fields that
    #: must always agree are two chances for them to disagree, and the disagreement
    #: that stores a full AADHAAR is not one to discover in production.
    restricted: bool = False


@dataclass(frozen=True, slots=True)
class LicenceSpec:
    """One trading licence a company in this jurisdiction may hold."""

    kind: str
    label: str
    #: Requires a bounded platform verification window (``valid_to``). For drug
    #: licences this may be a verified-through date; it is not a declaration that
    #: the statutory licence automatically expires. See docs/company-setup.md.
    has_expiry: bool = False
    #: Legally required on the document. Resolved by ``posting_date``, so a reprint
    #: shows the licence that was valid then.
    prints_on_invoice: bool = False
    #: The item classification this licence permits. A line carrying this gate with
    #: no valid licence **rejects** the posting (docs/company.md §4.4).
    gates: str | None = None
    #: A gated operation must match a licence's stated channel. Empty means the
    #: jurisdiction has not yet defined a channel distinction for this kind.
    operations: tuple[str, ...] = ()
    #: Drug categories licensed by this form. An unclassified drug cannot be
    #: matched to a form merely because its sale channel matches.
    drug_classes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JurisdictionProfile:
    """Everything country-specific about a company, in one reviewable place."""

    country_code: str
    tax_systems: tuple[TaxSystemSpec, ...]
    #: How ``jurisdiction_code`` is scoped — see ``REGISTRATION_SCOPES``.
    tax_registration_is_per: str
    statutory_ids: tuple[StatutoryIdSpec, ...] = ()
    licences: tuple[LicenceSpec, ...] = ()
    #: The capabilities a company in this jurisdiction almost certainly wants, as
    #: ``billing_platform.features`` keys — what a setup form offers **already
    #: selected** (docs/company-features.md §3). A suggestion, never a decision:
    #: it is pre-selected and can be cleared before the company exists, and
    #: nothing is enabled that the caller did not then ask for.
    #:
    #: Here rather than in a client because a default is jurisdiction policy, and a
    #: list in one client is a list the other two will disagree with. Validated at
    #: import: every key exists, is offerable under one of this profile's tax
    #: systems, and brings its own ``requires`` with it.
    default_features: tuple[str, ...] = ()
    #: The statutory ceiling on a cash receipt, or ``None`` where there is none. A
    #: tenant may lower it and never raise it (docs/company.md §5.5).
    cash_receipt_limit: Decimal | None = None

    def tax_systems_by_key(self) -> dict[str, TaxSystemSpec]:
        """The tax-system specs keyed by ``tax_system``."""
        return {spec.tax_system: spec for spec in self.tax_systems}

    def statutory_ids_by_kind(self) -> dict[str, StatutoryIdSpec]:
        """The identifier specs keyed by ``kind``. Kinds are unique per profile,
        enforced at import."""
        return {spec.kind: spec for spec in self.statutory_ids}

    def licences_by_kind(self) -> dict[str, LicenceSpec]:
        """The licence specs keyed by ``kind``."""
        return {spec.kind: spec for spec in self.licences}


#: docs/company.md §3. Keyed by ISO 3166-1 alpha-2 country code.
JURISDICTION_PROFILES: Final[dict[str, JurisdictionProfile]] = {
    "IN": JurisdictionProfile(
        country_code="IN",
        # A GSTIN is 15 characters: two state digits, the holder's ten-character
        # PAN, an entity number (1-9, then A-Z; never 0), a literal `Z`, and a
        # mod-36 check character. A GST TDS deductor is registered against its TAN
        # instead (four letters, five digits, a letter) with a literal `D`; an
        # e-commerce operator's TCS registration is PAN-based with a literal `C`.
        tax_systems=(
            TaxSystemSpec(
                "gst_in",
                number_pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
                class_number_patterns=(
                    ("tds_deductor", r"^\d{2}[A-Z]{4}\d{5}[A-Z][1-9A-Z]D[0-9A-Z]$"),
                    ("tcs_collector", r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]C[0-9A-Z]$"),
                ),
                mod36_check=True,
                state_prefixed=True,
            ),
        ),
        # One GSTIN per state, which is why `company.state_code` is frozen after
        # first posting: it decides intra- versus inter-state GST on every invoice.
        tax_registration_is_per="state",
        statutory_ids=(
            StatutoryIdSpec(
                kind="pan",
                label="PAN",
                pattern=r"^[A-Z]{5}\d{4}[A-Z]$",
                required=True,
                prints_on_invoice=True,
            ),
            StatutoryIdSpec(kind="tan", label="TAN", pattern=r"^[A-Z]{4}\d{5}[A-Z]$"),
            # L or U, 5-digit industry code, 2-letter state, 4-digit year, 3-letter
            # ownership class, 6-digit registration number. docs/company.md §3
            # writes the first class as `[LUu]`, which is a typo: a CIN never starts
            # with a lowercase letter, and accepting one would store a value the
            # MCA portal rejects.
            StatutoryIdSpec(
                kind="cin",
                label="CIN",
                pattern=r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$",
            ),
            StatutoryIdSpec(kind="udyam", label="Udyam (MSME)"),
            StatutoryIdSpec(kind="iec", label="Import-Export Code"),
            # Twelve digits, and then the platform keeps four of them.
            StatutoryIdSpec(
                kind="aadhaar",
                label="Aadhaar",
                pattern=r"^\d{12}$",
                restricted=True,
            ),
        ),
        licences=(
            # Separate records allow a chemist to hold both retail forms. These
            # labels follow the Delhi Drugs Control licence-type checklist.
            LicenceSpec(
                kind="drug_licence_20",
                label="Drug Licence 20 (retail)",
                has_expiry=True,
                prints_on_invoice=True,
                gates="scheduled_drug",
                operations=("RETAIL",),
                drug_classes=("OTHER_THAN_C_C1_X",),
            ),
            LicenceSpec(
                kind="drug_licence_21",
                label="Drug Licence 21 (retail)",
                has_expiry=True,
                prints_on_invoice=True,
                gates="scheduled_drug",
                operations=("RETAIL",),
                drug_classes=("C_C1_EXCLUDING_X",),
            ),
            LicenceSpec(
                kind="drug_licence_20b",
                label="Drug Licence 20B (wholesale)",
                has_expiry=True,
                prints_on_invoice=True,
                gates="scheduled_drug",
                operations=("WHOLESALE",),
                drug_classes=("OTHER_THAN_C_C1_X",),
            ),
            LicenceSpec(
                kind="drug_licence_21b",
                label="Drug Licence 21B (wholesale)",
                has_expiry=True,
                prints_on_invoice=True,
                gates="scheduled_drug",
                operations=("WHOLESALE",),
                drug_classes=("C_C1_EXCLUDING_X",),
            ),
            LicenceSpec(
                kind="narcotic_licence",
                label="Narcotic Licence",
                has_expiry=True,
                gates="narcotic",
            ),
            LicenceSpec(
                kind="fssai",
                label="FSSAI",
                has_expiry=True,
                prints_on_invoice=True,
            ),
            LicenceSpec(kind="lut", label="LUT (zero-rated exports)", has_expiry=True),
        ),
        # §269ST. A real statutory rule, so a real column on `company` — never a
        # custom field (CLAUDE.md invariant 14).
        cash_receipt_limit=Decimal("200000.0000"),
        # Stock, because a company billing goods in India is the ordinary case and
        # finding the item quantity fields missing is the ordinary complaint.
        # `credit_limits` because B2B trade here runs on credit. `e_waybill`
        # because a consignment over ₹50,000 needs one whatever the turnover —
        # unlike `e_invoicing`, which starts at ₹5 crore AATO and needs IRP
        # credentials, so it is offered unselected rather than assumed.
        default_features=("inventory", "credit_limits", "e_waybill"),
    ),
    "GB": JurisdictionProfile(
        country_code="GB",
        # No `number_pattern`: see `TaxSystemSpec.number_pattern`.
        tax_systems=(TaxSystemSpec("vat_gb"),),
        tax_registration_is_per="country",
        statutory_ids=(
            StatutoryIdSpec(
                kind="company_number",
                label="Company Number",
                pattern=r"^\d{8}$|^[A-Z]{2}\d{6}$",
                required=True,
                prints_on_invoice=True,
            ),
            StatutoryIdSpec(kind="utr", label="UTR", pattern=r"^\d{10}$"),
        ),
        cash_receipt_limit=None,
        # The same two ordinary capabilities; the GST documents have no UK peer.
        default_features=("inventory", "credit_limits"),
    ),
}


@dataclass(frozen=True, slots=True)
class StoredStatutoryValue:
    """What a statutory identifier is allowed to leave behind.

    For a restricted kind ``value`` is ``None`` and that is not a degraded case —
    it is the whole design. ``value_last4`` plus
    ``company_statutory_id.verification_reference`` answers the only question the
    platform ever asks: was this holder verified.
    """

    value: str | None
    value_last4: str


def supported_countries() -> tuple[str, ...]:
    """The countries a company may be created in, sorted."""
    return tuple(sorted(JURISDICTION_PROFILES))


def profile(country_code: str) -> JurisdictionProfile:
    """The profile for a country, or a 422.

    An unsupported country is refused at company creation rather than accepted
    with an empty profile: an empty profile would require no statutory identifiers,
    offer no tax system, and fail every licence gate closed — a company that can be
    created and can never post.
    """
    try:
        return JURISDICTION_PROFILES[country_code]
    except KeyError:
        raise ValidationFailedError(
            f"no jurisdiction profile for {country_code!r}; supported: "
            f"{', '.join(supported_countries())}",
            fields={"country_code": "not a supported jurisdiction"},
        ) from None


def statutory_id_spec(country_code: str, kind: str) -> StatutoryIdSpec:
    """The spec for one statutory-identifier kind, or a 422."""
    known = profile(country_code).statutory_ids_by_kind()
    try:
        return known[kind]
    except KeyError:
        raise ValidationFailedError(
            f"{kind!r} is not a statutory identifier in {country_code}: expected one of "
            f"{', '.join(sorted(known))}",
            fields={"kind": f"not a statutory identifier in {country_code}"},
        ) from None


def licence_spec(country_code: str, kind: str) -> LicenceSpec:
    """The spec for one licence kind, or a 422."""
    known = profile(country_code).licences_by_kind()
    try:
        return known[kind]
    except KeyError:
        raise ValidationFailedError(
            f"{kind!r} is not a licence kind in {country_code}: expected one of "
            f"{', '.join(sorted(known)) or 'none'}",
            fields={"kind": f"not a licence kind in {country_code}"},
        ) from None


def required_statutory_kinds(country_code: str) -> tuple[str, ...]:
    """The identifier kinds a company in this jurisdiction cannot be completed
    without, sorted."""
    return tuple(sorted(spec.kind for spec in profile(country_code).statutory_ids if spec.required))


def gate_kinds(
    country_code: str,
    gate: str,
    *,
    operation: str | None = None,
    drug_class: str | None = None,
) -> tuple[str, ...]:
    """The licence kinds that satisfy one item gate and supplied operation/class, sorted.

    Empty means **no licence in this jurisdiction permits it**, which is a refusal
    rather than permission — see ``statutory.assert_company_can_issue``.
    """
    return tuple(
        sorted(
            spec.kind
            for spec in profile(country_code).licences
            if spec.gates == gate
            and (operation is None or not spec.operations or operation in spec.operations)
            and (drug_class is None or not spec.drug_classes or drug_class in spec.drug_classes)
        )
    )


def offered_tax_systems(country_code: str) -> tuple[str, ...]:
    """The tax systems a company in this jurisdiction may register under, sorted."""
    return tuple(sorted(spec.tax_system for spec in profile(country_code).tax_systems))


def tax_system_spec(country_code: str, tax_system: str) -> TaxSystemSpec:
    """The spec for one tax system in this jurisdiction, or a 422.

    ``vat_gb`` on an Indian company is not a preference to be honoured; it is a
    registration no Indian authority issued.
    """
    known = profile(country_code).tax_systems_by_key()
    try:
        return known[tax_system]
    except KeyError:
        raise ValidationFailedError(
            f"{tax_system} is not a tax system in {country_code}: expected one of "
            f"{', '.join(sorted(known))}",
            fields={"tax_system": f"not offered in {country_code}"},
        ) from None


def assert_tax_system_offered(country_code: str, tax_system: str) -> None:
    """Reject a tax system that does not exist in this jurisdiction."""
    tax_system_spec(country_code, tax_system)


def assert_tax_registration_number(
    country_code: str,
    tax_system: str,
    number: str,
    *,
    registration_class: str = DEFAULT_REGISTRATION_CLASS,
    state_tax_code: str | None = None,
) -> str:
    """Validate a registration number against the profile and return its stored form.

    Returns the normalized value rather than ``None`` so a caller cannot validate one
    string and store another — the shape that was checked is the shape that is kept.

    ``registration_class`` selects any class-specific shapes
    (``TaxSystemSpec.class_number_patterns``). ``state_tax_code`` is the
    jurisdiction's ``state.tax_jurisdiction_code``; for a ``state_prefixed`` system
    the number's first two characters must equal it. ``None`` skips only that one
    rule, for a caller that genuinely has no state — a caller that *has* one and
    omits it has switched the check off.
    """
    spec = tax_system_spec(country_code, tax_system)
    if registration_class not in REGISTRATION_CLASSES:
        raise ValidationFailedError(
            f"unknown registration class {registration_class!r}.",
            fields={"registration_class": "not a known registration class"},
        )
    normalized = normalize_statutory_value(number)

    patterns = spec.number_patterns_for(registration_class)
    if patterns and not any(re.fullmatch(p, normalized) for p in patterns):
        raise ValidationFailedError(
            f"this is not a valid {tax_system} registration number.",
            fields={"number": f"does not match the {tax_system} format"},
        )
    if not normalized:
        raise ValidationFailedError(
            "a registration number is required.",
            fields={"number": "empty"},
        )
    if spec.mod36_check and gstin_check_character(normalized[:-1]) != normalized[-1]:
        # The message deliberately does not reveal the expected character: that
        # would turn the endpoint into a check-character oracle for made-up numbers.
        raise ValidationFailedError(
            f"this {tax_system} registration number fails its check character; it has "
            "probably been mistyped.",
            fields={"number": "check character does not match"},
        )
    if spec.state_prefixed and state_tax_code is not None and normalized[:2] != state_tax_code:
        raise ValidationFailedError(
            f"this {tax_system} registration number belongs to a different state.",
            fields={
                "number": (
                    f"state prefix {normalized[:2]} does not match the jurisdiction's GST "
                    f"state code {state_tax_code}"
                )
            },
        )
    return normalized


#: The GSTIN alphabet, in code order: ``0``-``9`` are 0-9, ``A``-``Z`` are 10-35.
GSTIN_CHARSET: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_character(first14: str) -> str:
    """The mod-36 check character of a GSTIN's first fourteen characters.

    The GSTN algorithm: each character's code (its ``GSTIN_CHARSET`` index) is
    multiplied by a factor alternating 1, 2, 1, 2 from the left; each product
    contributes ``product // 36 + product % 36``; the check code is
    ``(36 - total % 36) % 36``. Raises ``ValueError`` for input that is not
    fourteen characters of the alphabet — a programming error, never user input,
    because callers check the shape first.
    """
    if len(first14) != 14 or any(char not in GSTIN_CHARSET for char in first14):
        raise ValueError("a GSTIN check character needs 14 characters of 0-9A-Z")
    total = 0
    for index, char in enumerate(first14):
        quotient, remainder = divmod(GSTIN_CHARSET.index(char) * (1 + index % 2), 36)
        total += quotient + remainder
    return GSTIN_CHARSET[(36 - total % 36) % 36]


def validate_gstin(
    number: str,
    *,
    state_tax_code: str | None,
    registration_class: str = DEFAULT_REGISTRATION_CLASS,
) -> str:
    """Validate an Indian GSTIN and return its normalized (stored) form, or a 422.

    **The one GSTIN implementation.** ``identity`` (company registrations) and
    ``accounting`` (party registrations) both call this, so a number one service
    accepts the other cannot reject.

    - ``number`` — as typed; spaces and hyphens are dropped and it is uppercased.
    - ``state_tax_code`` — the GST state code the number must start with: the
      ``state.tax_jurisdiction_code`` of the registration's state (Maharashtra
      ``"27"``). Keyword-only with no default so every caller decides; ``None``
      skips only the prefix rule, for a party whose state is genuinely unknown.
    - ``registration_class`` — a ``billing_platform.tax.REGISTRATION_CLASSES`` key
      (``billing_platform.tax.registration_class(tax_system, regime)`` derives it
      from a regime). ``"tds_deductor"`` additionally accepts the TAN-based shape
      ``SS`` + TAN + entity + ``D`` + check, and ``"tcs_collector"`` (an
      e-commerce operator) the TCS shape ``SS`` + PAN + entity + ``C`` + check.
      Every class accepts the PAN-based
      shape ``SS`` + PAN + entity + ``Z`` + check.

    Always checked: the shape (entity code ``0`` is never issued and is refused)
    and the mod-36 check character. Failures are ``ValidationFailedError`` with
    ``fields={"number": ...}`` (or ``registration_class`` for an unknown class),
    and never echo the number.
    """
    return assert_tax_registration_number(
        "IN",
        "gst_in",
        number,
        registration_class=registration_class,
        state_tax_code=state_tax_code,
    )


def normalize_statutory_value(value: str) -> str:
    """The comparable form of an identifier as typed.

    Spaces and hyphens are how a human writes a twelve-digit number and are not
    part of the value. Uppercased because every identifier here is case-insensitive
    in practice, and a lowercase PAN stored beside its uppercase twin would defeat
    ``uq_company_statutory_id_company_id_kind_value_last4``.
    """
    return value.replace(" ", "").replace("-", "").strip().upper()


def prepare_statutory_value(country_code: str, kind: str, value: str) -> StoredStatutoryValue:
    """Validate an identifier and return only the part that may be persisted.

    **This is the single place the AADHAAR rule is implemented** (CLAUDE.md §5.10).
    Every caller in every service goes through it, because a second code path that
    writes ``company_statutory_id.value`` directly is the whole failure: the full
    number is never persisted, never logged, never returned by an API, and never
    exported, and the only way to hold that line is for the discard to happen
    before the value reaches a model at all.

    The pattern is checked *before* the discard, so a restricted identifier is
    still validated — verifying the wrong number is worse than not verifying.
    """
    spec = statutory_id_spec(country_code, kind)
    normalized = normalize_statutory_value(value)

    if spec.pattern is not None and re.fullmatch(spec.pattern, normalized) is None:
        raise ValidationFailedError(
            f"{spec.label} is not in the expected format.",
            # The rejected value is deliberately absent from the message: for a
            # restricted kind it would put a full AADHAAR into an error response
            # and, from there, into whatever logs the client's failures.
            fields={"value": f"does not match the {country_code} {kind} format"},
        )

    if len(normalized) < 4:
        raise ValidationFailedError(
            f"{spec.label} is too short to be an identifier.",
            fields={"value": "fewer than four characters"},
        )

    return StoredStatutoryValue(
        value=None if spec.restricted else normalized,
        # Populated for *every* kind, not only restricted ones. It is the last
        # column of `uq_company_statutory_id_company_id_kind_value_last4`, and
        # MariaDB treats NULLs in a unique key as distinct
        # (docs/identity-db-plan.md §2) — leaving it NULL for unrestricted kinds
        # would let a company store the same PAN twice.
        value_last4=normalized[-4:],
    )


def _validate_profiles() -> None:
    """Boot check. Every failure mode here is silent at runtime and expensive.

    A country code that is not ISO-shaped is a profile nothing selects. An unknown
    tax system offers a registration no service can compute. A pattern that does
    not compile raises from inside the request that first validates against it. A
    duplicate ``kind`` shadows one spec with another, so which rules apply depends
    on tuple order. A restricted identifier that prints on an invoice is a full
    AADHAAR on a document — the one outcome this module exists to prevent. And a
    cash ceiling wider than the column silently truncates on insert.
    """
    for code, entry in JURISDICTION_PROFILES.items():
        if code != entry.country_code:
            raise ValueError(f"profile {code!r} declares country_code {entry.country_code!r}")
        if re.fullmatch(r"[A-Z]{2}", code) is None:
            raise ValueError(f"profile key {code!r} is not an ISO 3166-1 alpha-2 code")
        if not entry.tax_systems:
            raise ValueError(f"{code} offers no tax system, so no company there could register")
        _validate_kinds(code, [spec.tax_system for spec in entry.tax_systems], "tax system")
        for system in entry.tax_systems:
            if system.tax_system not in TAX_SYSTEMS:
                raise ValueError(f"{code} names unknown tax system {system.tax_system!r}")
            if system.number_pattern is not None:
                re.compile(system.number_pattern)
            if system.class_number_patterns and system.number_pattern is None:
                raise ValueError(
                    f"{code} {system.tax_system} has class shapes but no base pattern, so "
                    "the class shapes would never be checked"
                )
            for registration_class, pattern in system.class_number_patterns:
                if registration_class not in REGISTRATION_CLASSES:
                    raise ValueError(
                        f"{code} {system.tax_system} names unknown registration class "
                        f"{registration_class!r}"
                    )
                re.compile(pattern)
        if entry.tax_registration_is_per not in REGISTRATION_SCOPES:
            raise ValueError(
                f"{code} scopes registration by {entry.tax_registration_is_per!r}; "
                f"expected one of {sorted(REGISTRATION_SCOPES)}"
            )

        _validate_kinds(code, [spec.kind for spec in entry.statutory_ids], "statutory identifier")
        _validate_kinds(code, [spec.kind for spec in entry.licences], "licence")
        _validate_default_features(code, entry)

        for id_spec in entry.statutory_ids:
            if id_spec.pattern is not None:
                re.compile(id_spec.pattern)
            if not id_spec.label:
                raise ValueError(f"{code} statutory identifier {id_spec.kind!r} has no label")
            if id_spec.restricted and id_spec.prints_on_invoice:
                raise ValueError(
                    f"{code} statutory identifier {id_spec.kind!r} is restricted and cannot "
                    "print on an invoice: only its last four digits are ever stored"
                )
            if id_spec.restricted and id_spec.required:
                raise ValueError(
                    f"{code} statutory identifier {id_spec.kind!r} is restricted and cannot be "
                    "required: the platform has no basis to demand a personal identity number"
                )

        for licence in entry.licences:
            if not licence.label:
                raise ValueError(f"{code} licence {licence.kind!r} has no label")
            if licence.gates is not None and not licence.gates:
                raise ValueError(f"{code} licence {licence.kind!r} has an empty gate")

        limit = entry.cash_receipt_limit
        if limit is not None:
            # `is_finite` first: a NaN would make every comparison below raise
            # `InvalidOperation` instead of the readable error this check exists for.
            if not limit.is_finite():
                raise ValueError(f"{code} has a non-finite cash receipt limit {limit}")
            if limit <= 0:
                raise ValueError(f"{code} has a non-positive cash receipt limit {limit}")
            if limit > MONEY_MAX:
                raise ValueError(f"{code} cash receipt limit {limit} exceeds DECIMAL(19,4)")
            exponent = limit.as_tuple().exponent
            if not isinstance(exponent, int) or -exponent > MONEY_SCALE:
                raise ValueError(
                    f"{code} cash receipt limit {limit} has more than {MONEY_SCALE} decimals, "
                    "so MariaDB would truncate it on insert"
                )


def _validate_default_features(country_code: str, entry: JurisdictionProfile) -> None:
    """Boot check for ``default_features``.

    A key outside the catalogue is a capability no code honours. A key whose
    ``tax_systems`` exclude every system this jurisdiction offers would be
    pre-selected and then filtered out of the form — a default nobody could see,
    and an enable call the service would refuse. A dependency left out would have
    the form silently enable something the profile never named.

    **Order is part of the contract**, not a nicety: the list is served as written
    (``identity.services.company_choices``) so that a caller enabling them in turn
    never asks for a dependent before the feature it needs. Checking membership
    alone would let ``("e_waybill", "inventory")`` boot clean and ship a list that
    breaks exactly the caller the order exists for.
    """
    offered = {spec.tax_system for spec in entry.tax_systems}
    _validate_kinds(country_code, list(entry.default_features), "default feature")
    preceding: set[str] = set()
    for key in entry.default_features:
        feature = FEATURES.get(key)
        if feature is None:
            raise ValueError(f"{country_code} defaults to unknown feature {key!r}")
        if feature.tax_systems and not offered & set(feature.tax_systems):
            raise ValueError(
                f"{country_code} defaults to {key!r}, which is only offerable under "
                f"{sorted(feature.tax_systems)} and this jurisdiction offers {sorted(offered)}"
            )
        missing = sorted(set(feature.requires) - preceding)
        if missing:
            raise ValueError(
                f"{country_code} defaults to {key!r} without its dependencies {missing} "
                "before it"
            )
        preceding.add(key)


def _validate_kinds(country_code: str, kinds: list[str], what: str) -> None:
    duplicates = sorted({kind for kind in kinds if kinds.count(kind) > 1})
    if duplicates:
        raise ValueError(f"{country_code} declares {what} {duplicates} more than once")
    for kind in kinds:
        if not kind.replace("_", "").isalnum() or kind != kind.lower():
            raise ValueError(f"{country_code} {what} {kind!r} is not a lowercase snake_case code")


_validate_profiles()
