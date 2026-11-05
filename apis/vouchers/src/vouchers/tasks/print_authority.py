"""Print disclosure includes effective owner grants as well as native field policies."""

from billing_platform.authz import ScopePath, resolve_permissions
from billing_platform.db.types import utcnow

from vouchers.api.auth import Access
from vouchers.domain.configuration import digest
from vouchers.tasks.access import fingerprint as policy_fingerprint


def fingerprint(current: Access) -> str:
    return digest(
        {
            "fields": policy_fingerprint(current),
            "permissions": sorted(
                resolve_permissions(
                    current.actor.grants,
                    target=ScopePath(company_id=current.context.company_id),
                    on_date=utcnow().date(),
                )
            ),
            "groups": sorted(str(group) for group in current.actor.group_ids),
        }
    )
