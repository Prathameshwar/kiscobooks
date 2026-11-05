"""Company rules that come from the jurisdiction profile.

The profile itself — which identifiers exist, what they look like, which licences
gate what, the statutory cash ceiling — is ``billing_platform.jurisdiction``, because
``billing`` and ``payments`` read it from their own replicas. What lives here is the
**policy over a company's actual rows**: whether a limit the tenant typed is allowed,
whether the identifiers they supplied are the ones the jurisdiction demands, and
whether a value is even storable.

No framework and no ORM (CLAUDE.md §4). Every rule takes plain values and returns a
decision, and none of them takes an actor: none of these is a permission, and the
last one is a legal prohibition no role can lift.
"""

from __future__ import annotations

from collections.abc import Collection
from decimal import Decimal

from billing_platform.errors import ValidationFailedError
from billing_platform.jurisdiction import (
    REGISTRATION_SCOPES,
    StoredStatutoryValue,
    prepare_statutory_value,
    profile,
    required_statutory_kinds,
    statutory_id_spec,
)


def assert_cash_receipt_limit_allowed(
    *, country_code: str, cash_receipt_limit: Decimal | None
) -> None:
    """The "lowerable, never raisable" rule (docs/company.md §5.5).

    India's §269ST ceiling is ₹2,00,000. A tenant may set a stricter house rule and
    may not set a laxer one, because the ceiling is not the platform's policy — it is
    the law, and ``payments`` enforcing a higher number would be helping a company
    break it.

    ``None`` means *no limit*, so where the jurisdiction has a ceiling it is the one
    value that must be refused: it is the largest possible raise, and it is what a
    form that simply omitted the field would send.
    """
    ceiling = profile(country_code).cash_receipt_limit
    if ceiling is None:
        # No statutory ceiling here, so any limit including none at all is the
        # tenant's own commercial choice.
        return

    if cash_receipt_limit is None:
        raise ValidationFailedError(
            f"{country_code} caps a cash receipt at {ceiling}, so this cannot be unlimited.",
            fields={"cash_receipt_limit": f"required in {country_code}, at most {ceiling}"},
        )

    if cash_receipt_limit > ceiling:
        raise ValidationFailedError(
            f"{country_code} caps a cash receipt at {ceiling}. It may be lowered, never raised.",
            fields={"cash_receipt_limit": f"above the {country_code} statutory ceiling {ceiling}"},
        )


def assert_required_statutory_ids_present(*, country_code: str, kinds: Collection[str]) -> None:
    """Reject a company missing an identifier its jurisdiction demands.

    Checked against the *set of kinds the company holds*, not against a payload:
    identifiers arrive as separate rows over time, so the only meaningful question is
    what exists now.
    """
    missing = sorted(set(required_statutory_kinds(country_code)) - set(kinds))
    if missing:
        labels = ", ".join(statutory_id_spec(country_code, kind).label for kind in missing)
        raise ValidationFailedError(
            f"a company in {country_code} needs {labels}.",
            fields={kind: "required in this jurisdiction" for kind in missing},
        )


def plan_statutory_id(*, country_code: str, kind: str, value: str) -> StoredStatutoryValue:
    """Validate a submitted identifier and return only what may be persisted.

    A thin pass-through to ``prepare_statutory_value`` on purpose. The discard has to
    live in ``libs/platform`` because every service that ever accepts one must behave
    identically, and it has to be reachable from ``identity``'s domain because this is
    the service that writes the row — re-implementing it here is precisely the second
    code path CLAUDE.md §5.10 cannot survive.
    """
    return prepare_statutory_value(country_code, kind, value)


def assert_statutory_row_storable(
    *, country_code: str, kind: str, value: str | None, value_last4: str
) -> None:
    """The last gate before a ``company_statutory_id`` row is written.

    Deliberately redundant with ``plan_statutory_id``, and the redundancy is the
    point: this catches a caller that built the row some other way. A full AADHAAR
    reaching the table is not a bug to be found in review later — it is a legal
    exposure under the Aadhaar Act (docs/company.md §4.3), so it is checked again
    where the row is actually persisted.

    Takes no actor and no override. There is no role, including platform admin, that
    may store a personal identity number here.
    """
    spec = statutory_id_spec(country_code, kind)

    if spec.restricted and value is not None:
        raise ValidationFailedError(
            f"{spec.label} is a restricted identifier: only its last four digits may be stored.",
            # The offending value is not echoed — that is what put it at risk.
            fields={"value": "must be absent for a restricted identifier"},
        )

    if not spec.restricted and value is None:
        raise ValidationFailedError(
            f"{spec.label} is a business identifier and is stored in full.",
            fields={"value": "required for an unrestricted identifier"},
        )

    if len(value_last4) != 4:
        raise ValidationFailedError(
            f"{spec.label} must record its last four characters.",
            fields={"value_last4": "not four characters"},
        )

    if value is not None and not value.endswith(value_last4):
        raise ValidationFailedError(
            f"{spec.label}'s stored last four characters do not match its value.",
            fields={"value_last4": "inconsistent with value"},
        )


def assert_jurisdiction_code_allowed(
    *, country_code: str, jurisdiction_code: str, state_codes: Collection[str]
) -> None:
    """Reject a registration scoped to the wrong kind of place.

    India issues one GSTIN per state, the UK one VAT number per country, and
    ``company_tax_registration.jurisdiction_code`` holds whichever applies. There is
    no foreign key on that column precisely because no single target covers both
    (revision 0011), so this is the check that replaces it.

    ``state_codes`` is passed in rather than queried: this module touches no session,
    and the caller has already loaded the country's subdivisions.
    """
    scope = profile(country_code).tax_registration_is_per

    if scope == "country":
        if jurisdiction_code != country_code:
            raise ValidationFailedError(
                f"{country_code} registers tax per country, so the jurisdiction must be "
                f"{country_code}.",
                fields={"jurisdiction_code": f"expected {country_code}"},
            )
        return

    if scope == "state":
        if jurisdiction_code not in set(state_codes):
            raise ValidationFailedError(
                f"{jurisdiction_code!r} is not a state of {country_code}, and "
                f"{country_code} registers tax per state.",
                fields={"jurisdiction_code": f"not a state of {country_code}"},
            )
        return

    # Unreachable while the profile validator holds; kept so a new scope added to
    # `REGISTRATION_SCOPES` without a branch here fails loudly instead of silently
    # accepting anything.
    raise ValidationFailedError(  # pragma: no cover - guarded at import by the profile validator
        f"unsupported registration scope {scope!r}; expected one of {sorted(REGISTRATION_SCOPES)}",
        fields={"jurisdiction_code": "unsupported registration scope"},
    )
