"""Field access for the registered Identity company entity.

Layout does not authorize access. This adapter resolves tenant-filtered subjects,
checks changed values, and emits validated sparse responses inside the transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from billing_platform.authz import Scope, ScopePath, has_permission
from billing_platform.custom_fields import condition_fields, condition_matches
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import FieldPolicyRule, assert_fields_writable, denied_fields
from billing_platform.fields import registry
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Integer, Numeric, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.domain.field_registry import COMPANY_ENTITY_TYPE, COMPANY_RELATIONSHIP_FIELDS
from identity.models import (
    Company,
    CustomFieldDefinition,
    FieldPolicy,
    Role,
    RoleAssignment,
    UserGroup,
    UserGroupMember,
)


@dataclass
class CompanyAccess:
    policies: list[FieldPolicy]
    assignments: list[RoleAssignment]
    current: Actor
    custom_keys: frozenset[str] = frozenset()

    @classmethod
    async def load(cls, db: AsyncSession, current: Actor) -> CompanyAccess:
        groups = set(
            await db.scalars(
                select(UserGroupMember.user_group_id).where(
                    UserGroupMember.user_id == current.user_id
                )
            )
        ) | set(current.group_ids)
        groups = set(
            await db.scalars(
                select(UserGroup.id).where(UserGroup.id.in_(groups), UserGroup.is_active.is_(True))
            )
        )
        today = utcnow().date()
        assignments = list(
            await db.scalars(
                select(RoleAssignment)
                .join(Role)
                .where(
                    Role.is_active.is_(True),
                    RoleAssignment.is_active.is_(True),
                    RoleAssignment.valid_from <= today,
                    or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to >= today),
                    or_(
                        and_(
                            RoleAssignment.subject_type == "user",
                            RoleAssignment.subject_id == current.user_id,
                        ),
                        and_(
                            RoleAssignment.subject_type == "user_group",
                            RoleAssignment.subject_id.in_(groups),
                        ),
                    ),
                )
            )
        )
        policies = list(
            await db.scalars(
                select(FieldPolicy).where(
                    FieldPolicy.is_active.is_(True),
                    FieldPolicy.entity_type == COMPANY_ENTITY_TYPE,
                    or_(
                        and_(
                            FieldPolicy.subject_type == "user",
                            FieldPolicy.subject_id == current.user_id,
                        ),
                        and_(
                            FieldPolicy.subject_type == "user_group",
                            FieldPolicy.subject_id.in_(groups),
                        ),
                        and_(
                            FieldPolicy.subject_type == "role",
                            FieldPolicy.subject_id.in_({a.role_id for a in assignments}),
                        ),
                    ),
                )
            )
        )
        custom_keys = frozenset(
            await db.scalars(
                select(CustomFieldDefinition.key)
                .where(CustomFieldDefinition.entity_type == COMPANY_ENTITY_TYPE)
                .limit(4097)
            )
        )
        if len(custom_keys) > 4096:
            raise PermissionDeniedError("custom field resolution exceeds its bounded capacity")
        supported = (
            {"custom_field:" + key for key in custom_keys}
            | set(registry.get(COMPANY_ENTITY_TYPE).fields)
            | set(COMPANY_RELATIONSHIP_FIELDS)
        )
        if any(
            policy.field_key not in supported
            or policy.access not in {"read", "write"}
            or policy.effect not in {"allow", "deny"}
            for policy in policies
        ):
            raise PermissionDeniedError("field policy references an unsupported field")
        return cls(policies, assignments, current, custom_keys)

    @property
    def fingerprint(self) -> str:
        values = sorted(
            (
                str(p.id),
                str(p.updated_at),
                p.effect,
                p.access,
                p.field_key,
                p.scope_type,
                str(p.scope_id),
                json.dumps(p.condition, sort_keys=True),
            )
            for p in self.policies
        )
        roles = sorted(
            (str(a.id), str(a.updated_at), a.scope_type, str(a.scope_id)) for a in self.assignments
        )
        return hashlib.sha256(json.dumps([values, roles]).encode()).hexdigest()

    @property
    def condition_columns(self) -> frozenset[str]:
        fields: set[str] = set()
        for policy in self.policies:
            if policy.condition is not None:
                try:
                    fields.update(
                        condition_fields(
                            policy.condition, allowed=frozenset(Company.__table__.columns.keys())
                        )
                    )
                except ValidationFailedError as exc:
                    raise PermissionDeniedError(
                        "field policy condition cannot be evaluated"
                    ) from exc
        return frozenset(fields)

    def rules(self, target: ScopePath, values: dict[str, Any] | None) -> list[FieldPolicyRule]:
        result = []
        for policy in self.policies:
            if policy.subject_type == "role" and not any(
                a.role_id == policy.subject_id and target.includes(Scope(a.scope_type, a.scope_id))
                for a in self.assignments
            ):
                continue
            if policy.condition is not None:
                # Query access must be safe for every possible matching row. A conditional
                # deny can apply; a conditional allow cannot establish blanket access.
                if values is None:
                    if policy.effect == "allow":
                        continue
                else:
                    _ = self.condition_columns
                    if not condition_matches(
                        policy.condition,
                        values,
                        numeric_fields=frozenset(
                            column.key
                            for column in Company.__table__.columns
                            if isinstance(column.type, Integer | Numeric)
                        ),
                    ):
                        continue
            result.append(
                FieldPolicyRule(
                    policy.field_key,
                    policy.access,
                    policy.effect,
                    Scope(policy.scope_type, policy.scope_id),
                )
            )
        return result

    def values(self, row: Company) -> dict[str, Any]:
        return {name: getattr(row, name) for name in self.condition_columns}

    def assert_write(
        self, row: Company, incoming: dict[str, Any], *, creating: bool = False
    ) -> None:
        target = ScopePath(company_id=row.id)
        before = self.values(row)
        after = before | incoming
        changed = {
            key
            for key, value in incoming.items()
            if key != "custom_fields" and (creating or getattr(row, key) != value)
        }
        if "custom_fields" in incoming:
            changed.update(
                "custom_field:" + key
                for key, value in incoming["custom_fields"].items()
                if creating or (row.custom_fields or {}).get(key) != value
            )
        # Both sides prevent changing the condition field to escape a denial.
        for values in (before, after):
            assert_fields_writable(changed, rules=self.rules(target, values), target=target)

    def project(
        self, row: Company, schema: type[BaseModel], *, values: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        target = ScopePath(company_id=row.id)
        result = schema.model_validate(row if values is None else values).model_dump(mode="json")
        for key in denied_fields(
            result, rules=self.rules(target, self.values(row)), access="read", target=target
        ):
            result.pop(key)
        if isinstance(result.get("custom_fields"), dict):
            custom = result["custom_fields"]
            denied = denied_fields(
                {"custom_field:" + key for key in custom},
                rules=self.rules(target, self.values(row)),
                access="read",
                target=target,
            )
            result["custom_fields"] = {
                key: value
                for key, value in custom.items()
                if "custom_field:" + key not in denied and key in self.custom_keys
            }
        return result

    def response(
        self,
        row: Company,
        schema: type[BaseModel],
        *,
        status_code: int = 200,
        values: dict[str, Any] | None = None,
    ) -> JSONResponse:
        return JSONResponse(self.project(row, schema, values=values), status_code=status_code)

    def assert_query(self, fields: set[str], *, gated_by_read: bool = True) -> None:
        """Refuse a query that filters, searches or sorts on a read-denied field.

        ``gated_by_read`` must mirror **how the caller chose its rows**. The company list
        returns exactly the companies where ``company.read`` is held, so only those
        targets can produce a matching row and only those need checking. A list whose
        rows are chosen some other way — the session's own switcher list, which is
        derived from *any* authority in a company — has a wider row set than that gate,
        and skipping the check for the difference would leave a denied field searchable
        while it is correctly stripped from the response. That split is exactly what
        invariant 15 and api-conventions.md forbid: a prefix search is a read.
        """
        targets = {ScopePath()} | {
            ScopePath(company_id=p.scope_id) for p in self.policies if p.scope_type == "company"
        }
        targets |= {
            ScopePath(company_id=a.scope_id) for a in self.assignments if a.scope_type == "company"
        }
        targets |= {
            ScopePath(company_id=g.scope.scope_id)
            for g in self.current.grants
            if g.scope.scope_type == "company"
        }
        for target in targets:
            if gated_by_read and not has_permission(
                self.current.grants, "company.read", target=target, on_date=utcnow().date()
            ):
                continue
            if denied_fields(fields, rules=self.rules(target, None), access="read", target=target):
                raise PermissionDeniedError("query uses a read-denied field")
