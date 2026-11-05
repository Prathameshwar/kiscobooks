"""Shared native aggregate field checks, command evidence and scoped identities."""

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.evidence import audit_change
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldContext, FieldWriteChecks


class AggregateWork:
    def __init__(self, db: AsyncSession, actor: Actor, company: uuid.UUID, permission: str) -> None:
        self.db, self.actor, self.company, self.permission = db, actor, company, permission
        self.access = ConfigurationAccess(db, actor, company)
        self.changed: dict[str, set[str]] = {}
        self.checks: dict[str, FieldWriteChecks] = {}

    async def context(self, model: type[Any]) -> FieldContext:
        self.actor.require_scope(self.permission, target=ScopePath(company_id=self.company))
        return await self.access.context(model)

    async def authorize_values(
        self,
        model: type[Any],
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        *,
        all_fields: bool = False,
    ) -> frozenset[str]:
        context = await self.context(model)
        changed = frozenset(
            key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
        )
        if all_fields:
            changed |= frozenset(after)
        context.assert_writable(
            changed,
            before=before,
            after=after,
            checked=self.checks.setdefault(context.native.entity_type, FieldWriteChecks()),
        )
        return changed

    async def record(
        self, row: Any, before: Mapping[str, Any], action: str, *, all_fields: bool = False
    ) -> None:
        after = await self.access.values(row)
        changed = await self.authorize_values(type(row), before, after, all_fields=all_fields)
        if not changed:
            return
        entity = "catalog." + row.__tablename__
        self.changed.setdefault(entity, set()).update(changed)
        audit_change(
            self.db,
            self.actor,
            self.company,
            entity,
            row.id,
            action,
            changed,
            before=before,
            after=after,
        )

    def common(self) -> dict[str, Any]:
        return {
            "id": uuid7(),
            "tenant_id": self.actor.tenant_id,
            "company_id": self.company,
            "created_by": self.actor.user_id,
            "updated_by": self.actor.user_id,
        }
