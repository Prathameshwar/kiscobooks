"""Per-category send policy — a code catalogue, never tenant-authored (docs/notification.md §5).

Category decides three things independent of any tenant configuration:

* **opt-in default** when a subject has expressed no preference — transactional and
  operational messages default on (legitimate interest); marketing defaults off.
* **whether consent is required** — only marketing needs recorded consent.
* **whether suppression and preference apply at all** — a *security* alert is not
  suppressible and cannot be preference-disabled: you do not get to opt out of "your
  password was changed". Everything else honours suppression and preference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from billing_platform.errors import ValidationFailedError

from notification.domain.constants import CATEGORIES


@dataclass(frozen=True, slots=True)
class CategoryPolicy:
    default_opt_in: bool
    consent_required: bool
    #: Whether preference and suppression gates apply. False only for security.
    overridable: bool


_POLICY: Final[dict[str, CategoryPolicy]] = {
    "security": CategoryPolicy(default_opt_in=True, consent_required=False, overridable=False),
    "transactional": CategoryPolicy(default_opt_in=True, consent_required=False, overridable=True),
    "operational": CategoryPolicy(default_opt_in=True, consent_required=False, overridable=True),
    "marketing": CategoryPolicy(default_opt_in=False, consent_required=True, overridable=True),
}

# Every channel category must have a policy — a missing one is a boot-time bug, not a
# runtime surprise (mirrors the permission/feature catalogues).
assert set(_POLICY) == CATEGORIES, "category policy catalogue is out of sync with CATEGORIES"


def policy_for(category: str) -> CategoryPolicy:
    try:
        return _POLICY[category]
    except KeyError:
        raise ValidationFailedError(f"unknown notification category: {category!r}") from None
