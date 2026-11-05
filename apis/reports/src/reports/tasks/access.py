"""Complete-input authority for reconciliation; no totals over hidden facts."""

from billing_platform.authz import ScopePath
from billing_platform.errors import PermissionDeniedError
from reporting_contract.contract import digest

from reports.api.auth import Access

INPUT_PERMISSIONS = frozenset(
    {
        "report.read",
        "ledger.read",
        "accounting.finance.read",
        "accounting.head.read",
        "accounting.group.read",
        "accounting.account.read",
        "accounting.party.read",
        "accounting.setup.read",
        "period.read",
    }
)


def can_prepare_gst(current: Access) -> bool:
    target = ScopePath(company_id=current.context.company_id)
    return current.actor.impersonation_id is None and any(
        current.actor.allows_scope(permission, target=target)
        for permission in (
            "ledger.post_journal",
            "accounting.finance.manage",
            "report.definition.manage",
        )
    )


def authorize(current: Access, permission: str = "report.read") -> None:
    current.context.assert_current(current.actor, current.context.company_id)
    for required in INPUT_PERMISSIONS | {permission}:
        current.actor.require_scope(
            required, target=ScopePath(company_id=current.context.company_id)
        )
    # Complete-company output cannot filter away a denied contributing field/row.
    # Conditional rules are denied conservatively, never evaluated on partial facts.
    if any(
        policy.get("access") == "read" and policy.get("effect") == "deny"
        for policy in current.context.policies
    ):
        raise PermissionDeniedError("complete-input reports require all contributing fields")


def fingerprint(current: Access) -> str:
    return digest(
        {
            "tenant": str(current.actor.tenant_id),
            "company": str(current.context.company_id),
            "actor": str(current.actor.user_id),
            "policies": list(current.context.policies),
        }
    )
