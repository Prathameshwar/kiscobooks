"""Assignment rules and layout resolution (docs/invoice-design.md §5.2).

Resolution answers one question for a document about to be printed: *which layout?* The
order is fixed and deterministic, because two callers printing the same document must
get the same design:

1. candidate rules are **active**, match the ``voucher_kind``, and belong to this
   company or to the tenant;
2. a rule matches only if **every criterion it sets** equals the request's value — a
   rule pinned to one branch does not apply to another, and a request that does not
   state a branch does not match a branch-pinned rule;
3. candidates are ordered by ``priority`` descending, then by **specificity** — how many
   criteria the rule pins — then newest first, so a tie is never resolved by luck;
4. the first candidate whose template is still publishable wins; a candidate whose
   template has been archived or never published is **skipped** rather than failing the
   whole resolution;
5. with no usable rule, the company's most recently published template is used, and the
   response says so by returning ``assignment_rule_id: null``.

A rule is checked **when it is written**: its template must be visible to the company
writing it, and its pinned version must belong to that template. Reading is the hot path,
and a renderer must not be the thing that discovers a cross-company reference.
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from sqlalchemy import ColumnElement, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from design.models.template import (
    InvoiceTemplate,
    InvoiceTemplateAssignment,
    InvoiceTemplateVersion,
)
from design.schemas.assignments import (
    AssignmentCreate,
    AssignmentUpdate,
    ResolveTemplateRequest,
    ResolveTemplateResponse,
)
from design.schemas.canvas import CANVAS
from design.tasks.templates import get_template
from design.tasks.versions import get_version

#: The criteria a rule may pin. The count of pinned criteria is its specificity.
CRITERIA: tuple[str, ...] = (
    "voucher_type_id",
    "branch_id",
    "currency_code",
    "customer_tax_category",
)


def specificity(rule: InvoiceTemplateAssignment) -> int:
    """How many criteria this rule pins. A catch-all default scores 0."""
    return sum(1 for field in CRITERIA if getattr(rule, field) is not None)


def matches(rule: InvoiceTemplateAssignment, request: ResolveTemplateRequest) -> bool:
    """Every criterion the rule sets must equal the request's value."""
    return all(
        getattr(rule, field) is None or getattr(rule, field) == getattr(request, field)
        for field in CRITERIA
    )


async def create_assignment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    input_data: AssignmentCreate,
    user_id: uuid.UUID | None = None,
) -> InvoiceTemplateAssignment:
    """Write a routing rule, after proving the template it names is this company's."""
    template = await get_template(
        session, template_id=input_data.template_id, company_id=company_id
    )
    if template.voucher_kind is not None and template.voucher_kind != input_data.voucher_kind:
        raise ValidationFailedError(
            f"this template is designed for {template.voucher_kind} vouchers, "
            f"not {input_data.voucher_kind}",
            fields={"template_id": "Choose a template designed for this kind."},
        )
    if input_data.specific_version_id is not None:
        await get_version(
            session,
            version_id=input_data.specific_version_id,
            template_id=template.id,
        )

    duplicate = await session.execute(
        select(InvoiceTemplateAssignment.id).where(
            InvoiceTemplateAssignment.company_id == company_id,
            InvoiceTemplateAssignment.voucher_kind == input_data.voucher_kind,
            InvoiceTemplateAssignment.voucher_type_id == input_data.voucher_type_id,
            InvoiceTemplateAssignment.branch_id == input_data.branch_id,
            InvoiceTemplateAssignment.currency_code == input_data.currency_code,
            InvoiceTemplateAssignment.customer_tax_category == input_data.customer_tax_category,
            InvoiceTemplateAssignment.is_active.is_(True),
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise ConflictError("an active rule already matches exactly these criteria")

    assignment = InvoiceTemplateAssignment(
        tenant_id=tenant_id,
        company_id=company_id,
        voucher_kind=input_data.voucher_kind,
        voucher_type_id=input_data.voucher_type_id,
        branch_id=input_data.branch_id,
        currency_code=input_data.currency_code,
        customer_tax_category=input_data.customer_tax_category,
        template_id=template.id,
        specific_version_id=input_data.specific_version_id,
        priority=input_data.priority,
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def get_assignment(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    company_id: uuid.UUID,
) -> InvoiceTemplateAssignment:
    """One rule owned by this company. A tenant-wide rule is edited at tenant scope."""
    result = await session.execute(
        select(InvoiceTemplateAssignment).where(
            InvoiceTemplateAssignment.id == assignment_id,
            InvoiceTemplateAssignment.company_id.in_([company_id, SCOPE_ALL]),
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise NotFoundError("template assignment not found")
    return assignment


async def update_assignment(
    session: AsyncSession,
    *,
    assignment: InvoiceTemplateAssignment,
    input_data: AssignmentUpdate,
    user_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-prioritize or deactivate a rule.

    Criteria are immutable: a different set of criteria is a different rule, and editing
    one in place would rewrite the reason every document already resolved the way it did.
    """
    requested = input_data.model_dump(exclude_unset=True)
    if not requested:
        raise ValidationFailedError("no changes were supplied")
    before = {field: getattr(assignment, field) for field in requested}
    for field, value in requested.items():
        setattr(assignment, field, value)
    assignment.updated_by = user_id
    await session.flush()
    return before, {field: getattr(assignment, field) for field in before}


async def list_assignments(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    limit: int,
    voucher_kind: str | None = None,
    template_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    keyset: ColumnElement[bool] | None = None,
) -> list[InvoiceTemplateAssignment]:
    """Rules visible to this company, newest first.

    ``template_id`` answers "where is this design used?"; the template foreign key's own
    index serves it.
    """
    conditions: list[Any] = [InvoiceTemplateAssignment.company_id.in_([company_id, SCOPE_ALL])]
    if voucher_kind is not None:
        conditions.append(InvoiceTemplateAssignment.voucher_kind == voucher_kind)
    if template_id is not None:
        conditions.append(InvoiceTemplateAssignment.template_id == template_id)
    if not include_inactive:
        conditions.append(InvoiceTemplateAssignment.is_active.is_(True))
    if keyset is not None:
        conditions.append(keyset)
    result = await session.execute(
        select(InvoiceTemplateAssignment)
        .where(*conditions)
        .order_by(desc(InvoiceTemplateAssignment.created_at), desc(InvoiceTemplateAssignment.id))
        .limit(limit + 1)
    )
    return list(result.scalars().all())


async def _candidates(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    voucher_kind: str,
) -> list[InvoiceTemplateAssignment]:
    result = await session.execute(
        select(InvoiceTemplateAssignment).where(
            InvoiceTemplateAssignment.company_id.in_([company_id, SCOPE_ALL]),
            InvoiceTemplateAssignment.voucher_kind == voucher_kind,
            InvoiceTemplateAssignment.is_active.is_(True),
        )
    )
    rules = list(result.scalars().all())
    rules.sort(
        key=lambda rule: (rule.priority, specificity(rule), rule.created_at, rule.id),
        reverse=True,
    )
    return rules


async def _publishable(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    company_id: uuid.UUID,
    version_id: uuid.UUID | None,
    voucher_kind: str | None = None,
) -> tuple[InvoiceTemplate, InvoiceTemplateVersion] | None:
    """The template and version a candidate resolves to, or ``None`` if unusable.

    A design made for another kind is unusable for this one, whatever pointed at it.
    """
    result = await session.execute(
        select(InvoiceTemplate).where(
            InvoiceTemplate.id == template_id,
            InvoiceTemplate.company_id.in_([company_id, SCOPE_ALL]),
            InvoiceTemplate.status == "PUBLISHED",
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        return None
    if voucher_kind is not None and template.voucher_kind not in (None, voucher_kind):
        return None
    target = version_id or template.current_version_id
    if target is None:
        return None
    found = await session.execute(
        select(InvoiceTemplateVersion).where(
            InvoiceTemplateVersion.id == target,
            InvoiceTemplateVersion.template_id == template.id,
        )
    )
    version = found.scalar_one_or_none()
    return None if version is None else (template, version)


def _response(
    template: InvoiceTemplate,
    version: InvoiceTemplateVersion,
    rule_id: uuid.UUID | None,
) -> ResolveTemplateResponse:
    return ResolveTemplateResponse(
        template_id=template.id,
        template_code=template.code,
        template_name=template.name,
        version_id=version.id,
        version_number=version.version_number,
        layout_digest=version.layout_digest,
        layout_definition=CANVAS.validate_python(version.layout_definition),
        assignment_rule_id=rule_id,
    )


async def resolve_template(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    request: ResolveTemplateRequest,
) -> ResolveTemplateResponse:
    """The layout this document prints on. See this module's docstring for the order."""
    for rule in await _candidates(
        session, company_id=company_id, voucher_kind=request.voucher_kind
    ):
        if not matches(rule, request):
            continue
        resolved = await _publishable(
            session,
            template_id=rule.template_id,
            company_id=company_id,
            version_id=rule.specific_version_id,
            voucher_kind=request.voucher_kind,
        )
        if resolved is not None:
            return _response(*resolved, rule.id)

    fallback = await session.execute(
        select(InvoiceTemplate)
        .where(
            InvoiceTemplate.company_id.in_([company_id, SCOPE_ALL]),
            InvoiceTemplate.status == "PUBLISHED",
            InvoiceTemplate.current_version_id.is_not(None),
        )
        .order_by(desc(InvoiceTemplate.updated_at), desc(InvoiceTemplate.id))
    )
    for template in fallback.scalars().all():
        resolved = await _publishable(
            session,
            template_id=template.id,
            company_id=company_id,
            version_id=template.current_version_id,
            voucher_kind=request.voucher_kind,
        )
        if resolved is not None:
            return _response(*resolved, None)

    raise NotFoundError(f"no published template resolves for voucher kind '{request.voucher_kind}'")
