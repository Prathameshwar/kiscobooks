"""Retention floors per category (docs/audit.md §6, §7 decision).

Defaults: ``security`` and ``money`` 7 years, ``admin`` 3, ``access`` and ``system`` 1.
A jurisdiction may extend these; nothing shortens them, because the table is
append-only and expiry only ever drops whole partitions (§4.1).

A monthly partition mixes categories, so it can be dropped only when the *longest-lived*
category it could contain has expired — :func:`max_retention_days`. Dropping on the
shortest floor would destroy 7-year ``security`` rows after 1 year.
"""

from __future__ import annotations

from audit.config import Settings
from audit.domain.categories import RETENTION_SETTING_BY_CATEGORY


def retention_days(category: str, settings: Settings) -> int:
    """The retention floor in days for ``category``.

    Raises on an unknown category rather than defaulting: a silent default here would let
    a mistyped category expire on the wrong schedule.
    """
    attribute = RETENTION_SETTING_BY_CATEGORY.get(category)
    if attribute is None:
        raise ValueError(f"no retention floor defined for category: {category}")
    return int(getattr(settings, attribute))


def max_retention_days(settings: Settings) -> int:
    """The longest floor across every category — the safe basis for dropping a partition."""
    return max(
        int(getattr(settings, attribute))
        for attribute in RETENTION_SETTING_BY_CATEGORY.values()
    )
