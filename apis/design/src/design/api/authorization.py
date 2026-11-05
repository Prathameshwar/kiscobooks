"""Per-route authorization (CLAUDE.md §5.1, §5.2).

Every route declares a permission **and** the object it is about. The endpoint key alone
is not enough: a user holding ``design.template.manage`` for company A must not reach
company B's template, so the check is always ``require_scope(key, target)`` against the
object's own company — never ``require(key)``.

Two scopes exist here because the data has two scopes:

* a **company-owned** row is checked against that company;
* a **tenant-wide** row (``company_id == SCOPE_ALL`` — the shared house style every
  company inherits) is checked against ``ScopePath()``, which only a tenant-scoped grant
  satisfies. Writing one from a company-scoped grant would let one company's
  administrator change every company's documents.
"""

from __future__ import annotations

import uuid

from billing_platform.authz import ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor

TEMPLATE_READ = "design.template.read"
TEMPLATE_MANAGE = "design.template.manage"
TEMPLATE_PUBLISH = "design.template.publish"
ASSIGNMENT_READ = "design.assignment.read"
ASSIGNMENT_MANAGE = "design.assignment.manage"
ASSET_READ = "design.asset.read"
ASSET_MANAGE = "design.asset.manage"
COMPONENT_READ = "design.component.read"
COMPONENT_MANAGE = "design.component.manage"
RENDER_READ = "design.render.read"
RENDER_RECORD = "design.render.record"


def company_scope(company_id: uuid.UUID) -> uuid.UUID:
    """Reject the tenant-wide sentinel in a path.

    ``/v1/companies/00000000-.../templates`` would otherwise read as "every company",
    and ``ScopePath`` refuses that id for the same reason.
    """
    if company_id == SCOPE_ALL:
        raise ValidationFailedError("a company id is required")
    return company_id


def require(actor: Actor, permission: str, company_id: uuid.UUID) -> None:
    """The caller must hold ``permission`` over this company."""
    actor.require_scope(permission, target=ScopePath(company_id=company_scope(company_id)))


def require_tenant(actor: Actor, permission: str) -> None:
    """The caller must hold ``permission`` tenant-wide, for a shared row."""
    actor.require_scope(permission, target=ScopePath())


def require_owner(actor: Actor, permission: str, owner_company_id: uuid.UUID) -> None:
    """Authorize against the **row's** owner, which is what §5.2 actually asks for."""
    if owner_company_id == SCOPE_ALL:
        require_tenant(actor, permission)
    else:
        require(actor, permission, owner_company_id)
