"""Historical read policies for the authenticated reader, including scoped role grants."""

from typing import Any

from billing_platform.errors import ValidationFailedError
from fastapi import Request
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import FieldPolicy
from identity.services.field_subjects import policy_subjects


async def historical_read_policies(db: AsyncSession, current: Actor) -> list[dict[str, Any]]:
    groups, assignments = await policy_subjects(db, current)
    roles = {row.role_id for row in assignments}
    policies = list(
        await db.scalars(
            select(FieldPolicy)
            .where(
                or_(
                    FieldPolicy.entity_type.startswith("accounting."),
                    FieldPolicy.entity_type.startswith("catalog."),
                    FieldPolicy.entity_type.startswith("vouchers."),
                ),
                FieldPolicy.is_active.is_(True),
                FieldPolicy.access == "read",
                or_(
                    and_(
                        FieldPolicy.subject_type == "user",
                        FieldPolicy.subject_id == current.user_id,
                    ),
                    and_(
                        FieldPolicy.subject_type == "user_group", FieldPolicy.subject_id.in_(groups)
                    ),
                    and_(FieldPolicy.subject_type == "role", FieldPolicy.subject_id.in_(roles)),
                ),
            )
            .limit(513)
        )
    )
    if len(policies) > 512:
        raise ValidationFailedError("audit policy context exceeds its bound")
    result = []
    for row in policies:
        value = {
            "entity_type": row.entity_type,
            "field_key": row.field_key,
            "effect": row.effect,
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id),
            "conditional": row.condition is not None,
        }
        if row.subject_type == "role":
            for assignment in assignments:
                if assignment.role_id == row.subject_id:
                    result.append(
                        value
                        | {
                            "subject_scope_type": assignment.scope_type,
                            "subject_scope_id": str(assignment.scope_id),
                        }
                    )
        else:
            result.append(value)
        if len(result) > 512:
            raise ValidationFailedError("audit policy context exceeds its bound")
    return result


async def historical_read_scope(
    db: AsyncSession, request: "Request", current: Actor
) -> dict[str, str | None]:
    """Validate the original Audit query, then bind its company into the signed context."""
    import uuid
    from urllib.parse import parse_qs, urlsplit

    from identity.models import Company
    from identity.services.step_up import StepUpRequiredError, require_company

    query = parse_qs(
        urlsplit(request.headers.get("x-original-uri", "")).query, keep_blank_values=True
    )
    values = query.get("company_id", [])
    if len(values) > 1:
        raise ValidationFailedError("company_id must occur only once")
    if values:
        try:
            company_id = uuid.UUID(values[0])
            if not company_id.int:
                raise ValueError("wildcard company")
        except ValueError as exc:
            raise ValidationFailedError("invalid company identifier") from exc
        await require_company(db, request, current, company_id)
        return {"company_id": str(company_id)}
    protected = await db.scalar(
        select(Company.id).where(Company.requires_step_up.is_(True)).limit(1)
    )
    if protected is not None:
        raise StepUpRequiredError("select a company and complete its authentication to read audit")
    return {"company_id": None}
