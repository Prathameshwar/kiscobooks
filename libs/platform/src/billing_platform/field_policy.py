"""Field-level access resolution — the layer that narrows a permitted update.

docs/field-permissions.md §6. This sits *under* endpoint permission and object scope: a
biller may hold ``invoice.update`` and still be denied changing the bill date or the
price. It is the third distinct control, and it has three rules that must all hold:

1. **Default is allow** — a deliberate deviation from deny-by-default (§6). The endpoint
   permission is the gate; field policy only *subtracts*, so a field with no matching
   policy is writable.
2. **Deny wins at equal specificity** — two policies at the same scope, one allow one
   deny, resolve to deny.
3. **More specific scope overrides broader** — a company-scope allow overrides a
   tenant-scope deny (and a department-scope rule overrides both).

Enforced on the **diff against current state**, never on payload presence (§6): sending
an unchanged value for a denied field is fine; *changing* it is not. No framework, no
ORM — the caller resolves the actor's applicable policies (from the ``field_policy``
replica) into ``FieldPolicyRule`` values and passes the changed-field set.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from billing_platform.authz import Scope, ScopePath
from billing_platform.errors import PermissionDeniedError

READ = "read"
WRITE = "write"
_DENY = "deny"
_ALLOW = "allow"


@dataclass(frozen=True, slots=True)
class FieldPolicyRule:
    """One ``field_policy`` row reduced to what resolution reads."""

    field_key: str
    access: str  # READ | WRITE
    effect: str  # _ALLOW | _DENY
    scope: Scope


def resolve_field_effect(
    rules: Iterable[FieldPolicyRule], *, field_key: str, access: str, target: ScopePath
) -> str:
    """The effect for one field, at ``target``. ``allow`` unless a deny wins."""
    applicable = [
        r
        for r in rules
        if r.field_key == field_key and r.access == access and target.includes(r.scope)
    ]
    if not applicable:
        return _ALLOW
    # Most specific scope wins; at equal specificity, deny wins (rules 2 and 3).
    scopes = target.scopes()
    most_specific = max(scopes.index(r.scope) for r in applicable)
    winners = [r for r in applicable if scopes.index(r.scope) == most_specific]
    return _DENY if any(r.effect == _DENY for r in winners) else _ALLOW


def denied_fields(
    changed_fields: Iterable[str],
    *,
    rules: Iterable[FieldPolicyRule],
    access: str,
    target: ScopePath,
) -> list[str]:
    """The changed fields the actor may not touch at ``access``, sorted."""
    rules = list(rules)
    return sorted(
        field
        for field in set(changed_fields)
        if resolve_field_effect(rules, field_key=field, access=access, target=target) == _DENY
    )


def assert_fields_writable(
    changed_fields: Iterable[str], *, rules: Iterable[FieldPolicyRule], target: ScopePath
) -> None:
    """403 if any *changed* field is write-denied. Names the fields — a client needs to
    know what it may not change — and nothing about which policy denied them (§5.8)."""
    denied = denied_fields(changed_fields, rules=rules, access=WRITE, target=target)
    if denied:
        raise PermissionDeniedError(f"you may not change these fields: {', '.join(denied)}")
