"""Facts Catalog refuses to store, whatever a tenant chooses to call them.

docs/catalog-warehouses.md §1 and docs/catalog-inventory-integration.md §2. Catalog owns what
a stock location *is*; the quantity in it, the lot on the shelf, the count sheet and the
transfer are Accounting's. Pure: no session, no ORM, no clock.

Every HTTP surface already refuses an unknown field — Pydantic's ``extra="forbid"`` on the
API, ``unknown or duplicate command column`` on an import file. The gap this closes is the one
place a tenant can legitimately add a *new* field name: a custom field definition. Naming one
``on_hand`` would give a company a second, unauthoritative stock balance that nothing
reconciles, nothing posts from and nothing can be trusted to have kept current — and
CLAUDE.md §6.14 means no domain rule would ever read it, so it would silently disagree with
the real quantity forever.

Matching is by **whole word sequence**, never substring. ``exception_handler`` contains the
letters of ``on_hand`` and is not a stock fact; ``onHand``, ``on-hand``, ``ON HAND`` and
``on_hands`` all are. A substring rule would reject ordinary names and, worse, teach whoever
hit it to spell around the check.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Sequence
from typing import Final

from billing_platform.errors import ValidationFailedError

#: Phrases that name a quantity, physical unit or stock event Accounting owns. Grouped by what
#: each family is, because the reason for refusing differs:
#:
#: * a **balance** would be a second stock figure nothing reconciles;
#: * an **opening** figure is a posted movement, not a definition;
#: * a **lot or serial** is a physical thing in a location, not a property of the product;
#: * a **transfer, count or adjustment** is a physical effect, not a Catalog definition.
#:
#: Deliberately not a wildcard on "stock" or "quantity": a replenishment band is a quantity
#: Catalog does own, and a tenant naming a field ``preferred_pack_quantity`` is describing its
#: product, not counting its shelves.
STOCK_FACT_PHRASES: Final[tuple[tuple[str, ...], ...]] = (
    # Balances and availability
    ("on", "hand"),
    ("in", "stock"),
    ("stock", "quantity"),
    ("stock", "balance"),
    ("stock", "level"),
    ("stock", "value"),
    ("current", "stock"),
    ("closing", "stock"),
    ("available", "quantity"),
    ("free", "quantity"),
    ("reserved", "quantity"),
    ("allocated", "quantity"),
    # Opening figures
    ("opening", "stock"),
    ("opening", "quantity"),
    ("opening", "balance"),
    # Physical lots and serials
    ("lot", "number"),
    ("lot", "quantity"),
    ("batch", "number"),
    ("batch", "quantity"),
    ("expiry", "date"),
    ("expiration", "date"),
    ("mfg", "date"),
    ("lot", "expiry"),
    ("batch", "expiry"),
    ("manufacture", "date"),
    ("best", "before", "date"),
    ("printed", "mrp"),
    ("pack", "mrp"),
    ("serial", "number"),
    # Movements and documents
    ("stock", "transfer"),
    ("transfer", "quantity"),
    ("stock", "count"),
    ("physical", "count"),
    ("cycle", "count"),
    ("counted", "quantity"),
    ("stock", "adjustment"),
    ("adjustment", "quantity"),
)

_SPLIT: Final[re.Pattern[str]] = re.compile(r"[^0-9A-Za-z]+|(?<=[a-z0-9])(?=[A-Z])")


def _singular(token: str) -> str:
    """Enough plural handling to stop ``on_hands`` and ``stock_quantities`` slipping through.

    Crude on purpose. It only has to make the reserved phrases unspellable in the plural; a
    token it mangles (``status`` becomes ``statu``) matches no phrase either way.
    """
    if token.endswith("ies") and len(token) > 3:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def words(key: str) -> tuple[str, ...]:
    """A field key as lower-case singular words: ``lotNumbers`` -> ``('lot', 'number')``."""
    return tuple(_singular(part.lower()) for part in _SPLIT.split(key) if part)


def stock_fact(key: str) -> tuple[str, ...] | None:
    """The reserved phrase this key names, or ``None``.

    Returns the phrase rather than a boolean so a caller can say *which* fact it refused —
    the reader has to change a definition, and "invalid field" would not tell them what to
    change it to.
    """
    tokens = words(key)
    for phrase in STOCK_FACT_PHRASES:
        span = len(phrase)
        if any(tokens[start : start + span] == phrase for start in range(len(tokens) - span + 1)):
            return phrase
    return None


#: One wording for every surface. The caller is being told where the fact lives, not merely
#: that their field was rejected: "invalid field" would read as a naming rule to work around.
MESSAGE: Final[str] = (
    "stock quantities, lots, counts and transfers belong to inventory, not Catalog"
)


def _detail(phrase: tuple[str, ...]) -> str:
    return " ".join(phrase) + " is an inventory fact Catalog does not store"


def assert_no_stock_facts(keys: Iterable[str], *, reserved: Collection[str] = ()) -> None:
    """Refuse a write whose field names claim a stock fact, naming the first one found.

    422 rather than a silent drop: a quantity field that was accepted and ignored is the
    failure this exists to prevent — the caller would believe Catalog holds a balance, and
    nothing would ever contradict them (docs/catalog-warehouse-plan.md, C7.11).

    Sorted so a body with two offending keys reports the same one every time; a caller
    fixing what the response named must not be handed a different name on the retry.

    ``reserved`` lets a caller exempt names it owns natively. Nothing uses it today; it is
    here so a future native column called, say, ``opening_stock_warehouse_id`` does not have
    to be spelled around.
    """
    for key in sorted(keys):
        if key in reserved:
            continue
        phrase = stock_fact(key)
        if phrase is not None:
            raise ValidationFailedError(MESSAGE, fields={key: _detail(phrase)})


def assert_no_stock_fact_columns(columns: Sequence[str]) -> None:
    """Refuse an import file whose headers claim a stock fact, naming **every** one of them.

    Bulk already rejects an unknown command column, so a header only reaches a stock-fact
    check when it is otherwise plausible. Reporting all of them at once matters here in a way
    it does not for a single JSON body: a spreadsheet author fixing one header at a time would
    resubmit a large file per column, and each resubmission is another bounded upload.
    """
    offenders = {column: phrase for column in columns if (phrase := stock_fact(column)) is not None}
    if offenders:
        raise ValidationFailedError(
            MESSAGE, fields={column: _detail(phrase) for column, phrase in offenders.items()}
        )
