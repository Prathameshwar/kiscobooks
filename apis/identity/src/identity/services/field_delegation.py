"""One field-authority check for direct policies and indirect group access changes."""

import uuid
from dataclasses import dataclass, field
from typing import Literal

from billing_platform.authz import Scope, ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import FieldPolicyRule, denied_fields
from billing_platform.fields import registry
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.api.field_access import CompanyAccess
from identity.domain import accounting_fields, document_fields
from identity.domain.field_registry import COMPANY_ENTITY_TYPE, COMPANY_RELATIONSHIP_FIELDS
from identity.models import CustomFieldDefinition, FieldPolicy
from identity.services.accounting_context import accounting_policies
from identity.services.customization import definitions


@dataclass
class DelegationCache:
    """Per-request memo for the indirect checks, which ask the same question repeatedly.

    One group join can carry many role assignments, each with many role-subject
    policies, and **the actor's own field authority is the same for all of them** — it
    is resolved from their grants and policies, not from the subject's. Without this,
    a group with twenty roles and fifty policies each would load the actor's authority
    a thousand times in one request.

    Request-scoped by construction: the caller creates it and drops it, so a change
    committed by another request is never read from a stale copy.
    """

    company: CompanyAccess | None = None
    policies: dict[tuple[str, ScopePath], list[FieldPolicy]] = field(default_factory=dict)
    #: Active policies on a role subject, by role. The request holds the tenant lock
    #: (``api/dependencies``), so a row cannot change under a reused list.
    role_policies: dict[uuid.UUID, list[FieldPolicy]] = field(default_factory=dict)
    #: Checks already passed, so a policy repeated across assignments costs nothing.
    settled: set[tuple[str, str, str, ScopePath]] = field(default_factory=set)


def registered(entity_type: str) -> bool:
    """Whether a field policy's entity is one this installation still carries.

    The direct path never needs this — ``PolicyWrite`` rejects an unknown entity
    before a handler runs. The indirect paths read ``field_policy.entity_type`` as
    *stored*, so a policy left behind by a contract revision would otherwise turn
    every edit of the role that carries it into a 422 naming an entity the caller
    never mentioned. An unregistered entity is inert — no service can resolve a
    contract for it, so nothing can be delegated through it either.
    """
    return (
        entity_type == COMPANY_ENTITY_TYPE
        or entity_type in document_fields.contracts()
        or entity_type in accounting_fields.contracts()
    )


async def field_definition(
    db: AsyncSession,
    key: str,
    entity_type: str = COMPANY_ENTITY_TYPE,
    company_id: uuid.UUID | None = None,
) -> CustomFieldDefinition | None:
    if entity_type in document_fields.contracts():
        if key in document_fields.contract(entity_type)["fields"]:
            return None
    elif entity_type != COMPANY_ENTITY_TYPE:
        if key not in accounting_fields.contract(entity_type)["fields"]:
            raise ValidationFailedError("field is not registered")
        return None
    elif key in registry.get(COMPANY_ENTITY_TYPE).fields or key in COMPANY_RELATIONSHIP_FIELDS:
        return None
    if not key.startswith("custom_field:"):
        raise ValidationFailedError("field is not registered")
    row = next(
        (
            row
            for row in await definitions(db, company_id or SCOPE_ALL, entity_type)
            if row.key == key.removeprefix("custom_field:")
        ),
        None,
    )
    if row is None:
        raise ValidationFailedError("custom field is not registered in this scope")
    return row


async def assert_field_delegation(
    db: AsyncSession,
    current: Actor,
    *,
    entity_type: str,
    field_key: str,
    access: Literal["read", "write"],
    target: ScopePath,
    cache: DelegationCache | None = None,
) -> None:
    if cache is not None and (entity_type, field_key, access, target) in cache.settled:
        return
    external = entity_type in document_fields.contracts()
    current.require_scope(
        "field_policy.manage",
        target=target if external or entity_type == COMPANY_ENTITY_TYPE else ScopePath(),
    )
    permission = (
        ("company.read" if access == "read" else "company.update")
        if entity_type == COMPANY_ENTITY_TYPE
        else (document_fields if external else accounting_fields).contract(entity_type)[
            "permissions"
        ][access]
    )
    current.require_scope(permission, target=target)
    await field_definition(db, field_key, entity_type, target.company_id)
    if entity_type == COMPANY_ENTITY_TYPE:
        company_access = cache.company if cache is not None else None
        if company_access is None:
            company_access = await CompanyAccess.load(db, current)
            if cache is not None:
                cache.company = company_access
        rules = company_access.rules(target, None)
    else:
        prefix = (
            "vouchers."
            if entity_type.startswith("vouchers.")
            else "catalog."
            if external
            else "accounting."
        )
        rows = cache.policies.get((prefix, target)) if cache is not None else None
        if rows is None:
            rows = await accounting_policies(db, current, target, entity_prefix=prefix)
            if cache is not None:
                cache.policies[(prefix, target)] = rows
        # A conditional deny may apply to any record; a conditional allow cannot
        # establish authority to delegate unrestricted access.
        rules = [
            FieldPolicyRule(
                row.field_key, row.access, row.effect, Scope(row.scope_type, row.scope_id)
            )
            for row in rows
            if row.entity_type == entity_type and (row.condition is None or row.effect == "deny")
        ]
    if denied_fields({field_key}, rules=rules, access=access, target=target):
        raise PermissionDeniedError("you cannot delegate field access you do not hold")
    if cache is not None:
        cache.settled.add((entity_type, field_key, access, target))
