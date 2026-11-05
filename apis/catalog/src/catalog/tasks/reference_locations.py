"""ISO country and state codes on a company-owned place, refused in the application.

Two foreign keys guard the pair on every table that names a place — ``country_code`` to
``country.code``, and ``(country_code, state_code)`` to the state's unique key, which is what
makes ``IN`` with ``US-CA`` unrepresentable (``libs/platform`` ``reference_models.State``).
On InnoDB they do not add up to what they look like. Verified on MySQL 9.6: a row naming an
unknown country with a NULL ``state_code`` is **accepted**, while the same unknown country
with a state code beside it is refused by that very single-column constraint. SQLite refuses
both, so the local engine never reports the gap and a schema-only reference check silently
does less in production than it does in the test suite.

The constraints stay — they are the backstop for a direct write and for the pairing itself —
and this is the check a request actually meets. One rule, two masters: a manufacturing site
and a stock location both name a place, and the codes have to mean the same thing on each.

Deliberately scoped to what changed: a code withdrawn from ISO is deactivated rather than
deleted, so an already-stored value must keep letting the row be renamed. Only a reference the
write actually names — or re-selects by reactivating the row — is held to being active.
"""

from __future__ import annotations

from billing_platform.db.reference_models import Country, State
from billing_platform.errors import ValidationFailedError
from sqlalchemy.ext.asyncio import AsyncSession

#: The pair, in the order they are validated. Callers compare these against stored values to
#: decide whether the write named a reference at all.
LOCATION_CODES: tuple[str, ...] = ("country_code", "state_code")


async def assert_reference_location(
    db: AsyncSession, *, subject: str, country_code: str | None, state_code: str | None
) -> None:
    """The named codes must be seeded, active, and consistent with one another.

    Both lookups are primary-key gets against a tenant-exempt reference table, so this costs
    at most two cached row reads on the writes that name a place.

    A ``None`` country names no place and carries no state: the input models and a table check
    constraint both refuse a state without one, so there is nothing left to resolve here.
    """
    if country_code is None:
        return
    country = await db.get(Country, country_code)
    if country is None or not country.is_active:
        raise ValidationFailedError(f"{subject} country must be active")
    if state_code is None:
        return
    state = await db.get(State, state_code)
    if state is None or state.country_code != country_code or not state.is_active:
        raise ValidationFailedError(f"{subject} state must be active in the selected country")
