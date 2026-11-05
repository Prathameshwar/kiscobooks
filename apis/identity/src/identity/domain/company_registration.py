"""Writing a tax registration or a licence.

Resolution — what was in force on a ``posting_date`` — is
``billing_platform.statutory``, because ``billing`` needs it inside the posting
transaction and may not call ``identity`` to get it (CLAUDE.md invariant 7). What
lives here is the **write path**: what a new or amended row must satisfy before it
exists, which is ``identity``'s alone.

Three rules carry the weight.

**What a registration *is* is immutable after create** — ``tax_system``, ``regime``,
``number``, ``jurisdiction_code`` and ``valid_from`` (docs/company.md §4.2). Amending
any of them in place would silently reinterpret every document already issued under
the row: which framework and regime computed a filed return's figures, which GSTIN
printed on it, which state made it intra- or inter-state. A change is "close the old
row (``valid_to``), open a new one", which is what keeps it resolvable by
``posting_date`` afterwards. Only ``valid_to``, ``legal_name_on_registration``,
``registered_address_id`` and ``is_primary`` are amendable.

**Overlap is rejected here rather than by a constraint**, because no DDL can express
"no two rows with intersecting date ranges". The unique key on ``valid_from`` stops an
exact duplicate and nothing else, so this is the only thing standing between the
resolver and an answer that depends on row order. Overlap is checked per
``(tax_system, registration class, jurisdiction)``, so a regular GSTIN and a
TDS-deductor or ISD registration may run side by side in one state.

**At most one ``is_primary`` per ``(tax_system, jurisdiction)`` on any date**, across
classes: "the primary registration" must be a single answer wherever it is asked.

No framework and no ORM (CLAUDE.md §4), and no actor parameter anywhere: none of these
is a permission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any, Final

from billing_platform.errors import ConflictError, ImmutableFieldError, ValidationFailedError
from billing_platform.jurisdiction import (
    assert_tax_registration_number,
    licence_spec,
    normalize_statutory_value,
    tax_system_spec,
)
from billing_platform.statutory import (
    Licence,
    TaxRegistration,
    assert_no_overlap,
    assert_window_ordered,
)
from billing_platform.tax import get_regime

from identity.domain.company_immutability import changed_fields
from identity.domain.company_jurisdiction import assert_jurisdiction_code_allowed

#: docs/company.md §4.2. What a registration *is*; fixed for the life of the row.
REGISTRATION_IMMUTABLE_FIELDS: Final[frozenset[str]] = frozenset(
    {"tax_system", "regime", "number", "jurisdiction_code", "valid_from"}
)


def registration_changes(current: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    """The fields an amendment actually changes, mapped to their new values.

    Raises ``ImmutableFieldError`` (422, for every actor — not a permission) if any of
    ``REGISTRATION_IMMUTABLE_FIELDS`` would change. Judged on the diff, not on payload
    presence, so a client echoing the row back unchanged is not refused; ``number`` is
    compared in its normalized form for the same reason.
    """
    comparable = dict(incoming)
    if isinstance(comparable.get("number"), str):
        comparable["number"] = normalize_statutory_value(comparable["number"])
    changed = changed_fields(current, comparable)

    frozen = sorted(changed & REGISTRATION_IMMUTABLE_FIELDS)
    if frozen:
        raise ImmutableFieldError(
            f"{', '.join(frozen)} cannot be changed on a registration. Close this "
            "registration (set valid_to) and add a new one from the date the change "
            "took effect.",
            fields={name: "immutable after create" for name in frozen},
        )
    return {name: comparable[name] for name in sorted(changed)}


def assert_single_primary(registrations: Sequence[TaxRegistration]) -> None:
    """At most one ``is_primary`` row per ``(tax_system, jurisdiction_code)`` on any date.

    Checked across registration classes: a regular GSTIN and a TDS-deductor
    registration may coexist, but only one of them is "the" primary. 409 like overlap,
    because it is a conflict with another row rather than a malformed request.
    """
    grouped: dict[tuple[str, str], list[TaxRegistration]] = {}
    for registration in registrations:
        if registration.is_primary:
            key = (registration.tax_system, registration.jurisdiction_code)
            grouped.setdefault(key, []).append(registration)

    for (tax_system, jurisdiction_code), group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda registration: registration.valid_from)
        for earlier, later in pairwise(ordered):
            if earlier.valid_to is None or later.valid_from <= earlier.valid_to:
                raise ConflictError(
                    f"only one {tax_system} registration in {jurisdiction_code} may be "
                    f"primary on any date; {earlier.number} already is from "
                    f"{earlier.valid_from.isoformat()}. Unset is_primary on one of them.",
                )


def assert_registration_coexists(
    *, incoming: TaxRegistration, existing: Sequence[TaxRegistration]
) -> None:
    """The rules between a registration and the company's **other** registrations.

    ``existing`` excludes the row being amended, or an amendment would always be found
    to overlap itself. Used on its own by the amendment path, where the immutable
    fields have not changed and so need no re-validation.
    """
    assert_window_ordered(incoming.valid_from, incoming.valid_to, what="registration")
    rows = [*existing, incoming]
    assert_no_overlap(rows)
    assert_single_primary(rows)


def registration_class_of(incoming: TaxRegistration) -> str:
    """The ``registration_class`` stored on a new row: the regime's, by the catalogue.

    Stored rather than only derived so the unique key can group by it as the overlap
    rule does. Never taken from the request — it is a property of the regime, and the
    regime is immutable, so the stored class can never disagree with it.
    """
    return get_regime(incoming.tax_system, incoming.regime).registration_class


def assert_registration_writable(
    *,
    incoming: TaxRegistration,
    existing: Sequence[TaxRegistration],
    country_code: str,
    state_tax_codes: Mapping[str, str | None],
) -> str:
    """Everything a new registration must satisfy, and the number to store.

    ``state_tax_codes`` maps each of the country's state codes to its
    ``tax_jurisdiction_code`` (GST state code), or ``None`` where it has none. For a
    state-prefixed number (a GSTIN) the state must have one: a registration that
    cannot be checked against its state is refused rather than stored unchecked.

    Returns the normalized registration number so the caller stores the string that
    was validated rather than the one that was typed.
    """
    spec = tax_system_spec(country_code, incoming.tax_system)
    regime = get_regime(incoming.tax_system, incoming.regime)
    assert_jurisdiction_code_allowed(
        country_code=country_code,
        jurisdiction_code=incoming.jurisdiction_code,
        state_codes=state_tax_codes.keys(),
    )
    state_tax_code = state_tax_codes.get(incoming.jurisdiction_code)
    if spec.state_prefixed and state_tax_code is None:
        raise ValidationFailedError(
            f"{incoming.jurisdiction_code} has no {incoming.tax_system} state code, so a "
            "registration there cannot be checked.",
            fields={"jurisdiction_code": f"has no {incoming.tax_system} state code"},
        )
    assert_registration_coexists(incoming=incoming, existing=existing)
    return assert_tax_registration_number(
        country_code,
        incoming.tax_system,
        incoming.number,
        registration_class=regime.registration_class,
        state_tax_code=state_tax_code,
    )


def assert_licence_writable(*, incoming: Licence, country_code: str) -> None:
    """Everything a licence row must satisfy.

    The expiry check is the one worth stating: a licence the profile marks
    ``has_expiry`` must carry ``valid_to``. Left open-ended it would satisfy every
    posting gate forever, which turns the gate into decoration and is exactly the
    failure ``renewal_reminder_days`` and the Beat sweep exist to prevent.
    """
    spec = licence_spec(country_code, incoming.kind)
    assert_window_ordered(incoming.valid_from, incoming.valid_to, what="licence")

    if spec.has_expiry and incoming.valid_to is None:
        raise ValidationFailedError(
            f"{spec.label} requires a verified validity end date.",
            fields={"valid_to": "required for a bounded licence verification window"},
        )

    if not incoming.number.strip():
        raise ValidationFailedError(
            f"{spec.label} needs its licence number.",
            fields={"number": "empty"},
        )
