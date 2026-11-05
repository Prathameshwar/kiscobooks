"""Attachment scan gate (docs/notification.md §schema, Phase 9).

An attachment is registered as ``pending`` and only becomes sendable once a malware scan
marks it ``clean``. Associating anything else to a delivery is refused — an infected or
unscanned file must never leave the platform. Pure: the caller passes the status.
"""

from __future__ import annotations

from typing import Final

from billing_platform.errors import ValidationFailedError

SCAN_STATUSES: Final[frozenset[str]] = frozenset({"pending", "clean", "infected", "error"})


def assert_scan_status(scan_status: str) -> None:
    if scan_status not in SCAN_STATUSES:
        raise ValidationFailedError(
            "unknown scan status",
            fields={"scan_status": f"one of {', '.join(sorted(SCAN_STATUSES))}"},
        )


def assert_sendable(scan_status: str) -> None:
    """Only a clean attachment may be attached to a delivery."""
    if scan_status != "clean":
        raise ValidationFailedError(
            f"attachment is not clean (scan status: {scan_status})",
            fields={"scan_status": "must be clean before it can be sent"},
        )
