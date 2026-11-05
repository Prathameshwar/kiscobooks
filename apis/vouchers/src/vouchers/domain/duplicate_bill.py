"""Duplicate supplier-bill rules that need no database.

A supplier's own invoice number is typed by hand, so the same bill is easily entered twice with
different case or spacing. Both Tally Prime and QuickBooks warn when one supplier's bill number
is recorded again; this is that warning, made a stable, auditable refusal that the person at the
keyboard can confirm past.
"""

import unicodedata
from typing import Final

from billing_platform.errors import ConflictError

#: Statuses in which a bill still stands. A cancelled, rejected or reversed bill is gone and its
#: number may be entered again.
LIVE_STATUSES: Final = ("DRAFT", "SUBMITTED", "APPROVED", "ISSUED", "POSTED")
#: At most this many matching rows are shown or carried in an error.
MATCH_LIMIT: Final = 5
#: Hard ceiling on candidate rows read for one supplier (or one payable ledger) and fiscal year.
#: The walk is never silently cut short: when it stops here with rows left, the answer is marked
#: incomplete and submit refuses until the person acknowledges.
CANDIDATE_CEILING: Final = 20_000
#: Candidate rows fetched per keyset batch.
BATCH_SIZE: Final = 500

DUPLICATE_BILL_CODE: Final = "duplicate_supplier_bill"
ACKNOWLEDGED_NOTE: Final = "duplicate supplier bill acknowledged"
INCOMPLETE_NOTE: Final = "duplicate supplier bill check incomplete; acknowledged"
AUTOMATIC_APPROVAL_NOTE: Final = "approval not required by the voucher configuration"


class DuplicateSupplierBillError(ConflictError):
    """409 with a stable code: this supplier's bill number is already recorded."""

    code = DUPLICATE_BILL_CODE


#: Punctuation typed after or before a bill number that never distinguishes one bill from another.
_EDGE_PUNCTUATION: Final = " .,;:"
#: The minus sign is a symbol (Sm), not a dash (Pd), yet is typed and pasted as one.
_MINUS_SIGN: Final = chr(0x2212)


def normalize_bill_reference(value: str) -> str:
    """The comparison key for a supplier's own bill number.

    Compatibility-normalised (NFKC, so fullwidth letters and the non-breaking hyphen fold to their
    plain forms), invisible format characters dropped (zero-width space, joiner, byte-order mark,
    soft hyphen), every dash variant mapped to ``-``, whitespace runs collapsed, leading and
    trailing whitespace and ``.,;:`` removed, then case-folded. Digits, ``/`` and inner
    punctuation keep their meaning: ``0418`` and ``418``, or ``A/1`` and ``A-1``, stay different.
    """
    kept = (
        "-" if unicodedata.category(c) == "Pd" or c == _MINUS_SIGN else c
        for c in unicodedata.normalize("NFKC", value)
        if unicodedata.category(c) != "Cf"
    )
    return " ".join("".join(kept).split()).strip(_EDGE_PUNCTUATION).casefold()


def annotate(reason: str, *notes: str, limit: int = 500) -> str:
    """A transition reason carrying system notes; the person's own text yields to them."""
    suffix = "; ".join(notes)
    if not suffix:
        return reason
    own = reason.strip()
    if not own:
        return suffix[:limit]
    room = limit - len(suffix) - 3
    return f"{own[:room]} [{suffix}]" if room > 0 else suffix[:limit]
