"""Domain rules for invoice templates (docs/invoice-design.md §5.1).

The lifecycle lives here, not in the routes and not in the client:

* a template is created ``DRAFT`` and only publishing a version makes it ``PUBLISHED``;
* ``archive_template`` is this service's delete — the row stays because render snapshots
  point at it (CLAUDE.md invariant 12) — and it releases the code for reuse through the
  ``live_code`` generated column;
* a shipped (``is_system``) template is read-only to every actor, like a system role.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from sqlalchemy import ColumnElement, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from design.models.template import (
    InvoiceTemplate,
    InvoiceTemplateAssignment,
    InvoiceTemplateVersion,
)
from design.schemas.canvas import CanvasDefinition, CanvasV11
from design.schemas.templates import TemplateCreate, TemplateUpdate

#: Fields an update may touch. ``status`` is absent deliberately: a client that could
#: write it could mark a template live with no layout behind it.
UPDATABLE: tuple[str, ...] = (
    "name",
    "description",
    "paper_size",
    "page_orientation",
    "page_width_mm",
    "page_height_mm",
    "unit_of_measure",
    "voucher_kind",
    "line_profile",
)


#: Portrait millimetres per named stock. ``None`` height is continuous roll: a receipt
#: printer feeds as far as the content goes, so there is no page length to overflow — the
#: designer front end reached the same conclusion by rendering one (docs/invoice-design.md §9.4).
PAPER_MM: dict[str, tuple[float, float | None]] = {
    "A4": (210.0, 297.0),
    "LETTER": (215.9, 279.4),
    "A5": (148.0, 210.0),
    "THERMAL_80MM": (80.0, None),
    "THERMAL_58MM": (58.0, None),
}

#: A tenth of a millimetre. Layout geometry is ``float``, so a column set the editor laid out
#: to exactly fill its page can land a hair over after arithmetic; rejecting that would be a
#: rounding artefact masquerading as a validation rule.
_FIT_TOLERANCE_MM = 0.1


def page_extent(template: InvoiceTemplate) -> tuple[float, float | None]:
    """The sheet this template prints on, in millimetres, oriented.

    Read from the **row**, which is the only place paper size lives: the 1.1.0 canvas no
    longer restates it (see the decision log), so there is nothing here to disagree with.
    """
    if template.paper_size == "CUSTOM":
        width = float(template.page_width_mm or 0.0)
        height: float | None = float(template.page_height_mm or 0.0)
    else:
        width, height = PAPER_MM.get(template.paper_size, (0.0, None))
    if template.page_orientation == "LANDSCAPE" and height is not None:
        width, height = height, width
    return width, height


def assert_layout_fits(template: InvoiceTemplate, layout: CanvasDefinition) -> None:
    """Nothing in the layout may be wider or longer than the paper it prints on.

    **1.1.0 only, deliberately.** 1.0.0 is frozen in behaviour as well as in shape: a layout
    that saved yesterday must not start failing today, and a stored version is re-read on every
    resolve. New rules arrive with the version that introduced the geometry they police.

    This checks only what is *unrenderable* — a box off the edge of the sheet. Crowding the
    margin is a **warning**, and warnings are the editor's job: it lists them at the moment of
    publication, where a person can decide, which is not a decision a 422 can make for them.
    Continuous roll stock has no length to overflow, so only its width is bounded.
    """
    if not isinstance(layout, CanvasV11):
        return
    width, height = page_extent(template)
    if width <= 0:
        # Fail closed. This is unreachable today — `paper_size` is a six-value Literal and
        # `CUSTOM` is validated to carry both dimensions on create and on update — but the
        # alternative was *skipping* the fit check for a paper we could not measure, and a
        # validation rule that silently switches itself off is worse than one that is noisy.
        raise ValidationFailedError(
            "this template's paper size has no usable dimensions to check the layout against",
            fields={"paper_size": template.paper_size},
        )
    offenders: list[str] = []
    for section in layout.sections:
        boxes = [(section.id, section.x, section.y, section.width, section.height)]
        boxes += [
            (element.id, element.x, element.y, element.width, element.height)
            for element in section.elements
        ]
        for name, x, y, box_width, box_height in boxes:
            if x + box_width > width + _FIT_TOLERANCE_MM:
                offenders.append(f"{name} ends at {x + box_width:g}mm across a {width:g}mm page")
            elif height is not None and y + box_height > height + _FIT_TOLERANCE_MM:
                offenders.append(f"{name} ends at {y + box_height:g}mm down a {height:g}mm page")
    if offenders:
        raise ValidationFailedError(
            "the layout does not fit the paper this template prints on",
            fields={"layout_definition": "; ".join(offenders[:5])},
        )


def layout_digest(layout: CanvasDefinition) -> str:
    """SHA-256 over the layout's canonical JSON.

    ``json.dumps`` with sorted keys rather than ``billing_platform.idempotency``'s
    canonical encoder: layout geometry is ``float`` — display geometry, never money — and
    that encoder refuses floats by design. Python's float repr round-trips exactly, so
    the encoding is still stable for the same tree.
    """
    body = json.dumps(
        layout.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(body.encode()).hexdigest()


async def get_template(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    company_id: uuid.UUID,
    include_archived: bool = False,
) -> InvoiceTemplate:
    """One template visible to this company — its own, or a tenant-wide one.

    The tenant predicate comes from the session-level filter (CLAUDE.md §5.3); the
    company predicate is this function's job, and it is what stops a template id from one
    company being read through another company's path (§5.2).
    """
    conditions: list[Any] = [
        InvoiceTemplate.id == template_id,
        InvoiceTemplate.company_id.in_([company_id, SCOPE_ALL]),
    ]
    if not include_archived:
        conditions.append(InvoiceTemplate.status != "ARCHIVED")
    result = await session.execute(select(InvoiceTemplate).where(*conditions))
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("invoice template not found")
    return template


async def list_templates(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    limit: int,
    status: str | None = None,
    voucher_kind: str | None = None,
    keyset: ColumnElement[bool] | None = None,
) -> list[InvoiceTemplate]:
    """Newest first, company and tenant-wide rows together, archived rows excluded.

    Filtered by kind, a list holds the designs made for that kind and the ones that never said
    what they are for, since both may print it.
    """
    conditions: list[Any] = [
        InvoiceTemplate.company_id.in_([company_id, SCOPE_ALL]),
        InvoiceTemplate.status != "ARCHIVED",
    ]
    if status is not None:
        conditions.append(InvoiceTemplate.status == status)
    if voucher_kind is not None:
        conditions.append(
            or_(
                InvoiceTemplate.voucher_kind == voucher_kind, InvoiceTemplate.voucher_kind.is_(None)
            )
        )
    if keyset is not None:
        conditions.append(keyset)
    result = await session.execute(
        select(InvoiceTemplate)
        .where(*conditions)
        .order_by(desc(InvoiceTemplate.created_at), desc(InvoiceTemplate.id))
        .limit(limit + 1)
    )
    return list(result.scalars().all())


async def create_template(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    input_data: TemplateCreate,
    user_id: uuid.UUID | None = None,
) -> tuple[InvoiceTemplate, InvoiceTemplateVersion | None]:
    """Create a ``DRAFT`` template, optionally with version 1 of its canvas.

    The initial canvas is **not** published: a new template prints nothing until someone
    publishes a version, which is the act that changes what documents look like.
    """
    template = InvoiceTemplate(
        tenant_id=tenant_id,
        company_id=SCOPE_ALL if input_data.is_tenant_wide else company_id,
        name=input_data.name,
        code=input_data.code,
        description=input_data.description,
        paper_size=input_data.paper_size,
        page_orientation=input_data.page_orientation,
        page_width_mm=input_data.page_width_mm,
        page_height_mm=input_data.page_height_mm,
        unit_of_measure=input_data.unit_of_measure,
        voucher_kind=input_data.voucher_kind,
        line_profile=input_data.line_profile,
        status="DRAFT",
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(template)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"template code '{input_data.code}' is already in use") from exc

    version: InvoiceTemplateVersion | None = None
    if input_data.initial_canvas is not None:
        version = InvoiceTemplateVersion(
            tenant_id=tenant_id,
            template_id=template.id,
            version_number=1,
            schema_version=input_data.initial_canvas.schema_version,
            layout_definition=input_data.initial_canvas.model_dump(mode="json"),
            layout_digest=layout_digest(input_data.initial_canvas),
            change_summary="Initial template canvas",
            created_by=user_id,
        )
        session.add(version)
        await session.flush()
    return template, version


def assert_editable(template: InvoiceTemplate) -> None:
    """Shipped templates are read-only; archived ones are history.

    Not a permission check — *no* actor may edit either, which is why it lives in the
    domain rather than in a role (the same shape as CLAUDE.md §6.16's ratchet).
    """
    if template.is_system:
        raise ValidationFailedError(
            "a system template is read-only; copy it into a tenant template to change it"
        )
    if template.status == "ARCHIVED":
        raise ValidationFailedError("an archived template cannot be changed")


async def update_template(
    session: AsyncSession,
    *,
    template: InvoiceTemplate,
    input_data: TemplateUpdate,
    user_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply a metadata patch, returning the before/after values for the audit row."""
    assert_editable(template)
    requested = input_data.model_dump(exclude_unset=True)
    if not requested:
        raise ValidationFailedError("no changes were supplied")

    before = {field: getattr(template, field) for field in UPDATABLE if field in requested}
    for field in UPDATABLE:
        if field in requested:
            setattr(template, field, requested[field])
    if template.line_profile is not None and template.voucher_kind is None:
        raise ValidationFailedError("a line profile belongs to a voucher kind; name the kind too")
    if "voucher_kind" in requested and template.voucher_kind is not None:
        # A design re-purposed for another kind would keep printing the old kind's vouchers
        # through the rules that point at it; retire those rules first.
        routed = await session.execute(
            select(InvoiceTemplateAssignment.voucher_kind).where(
                InvoiceTemplateAssignment.template_id == template.id,
                InvoiceTemplateAssignment.is_active.is_(True),
                InvoiceTemplateAssignment.voucher_kind != template.voucher_kind,
            )
        )
        if routed.first() is not None:
            raise ConflictError(
                "active routing rules print another voucher kind on this template; "
                "retire them before changing what it is for"
            )
    if template.paper_size == "CUSTOM" and (
        template.page_width_mm is None or template.page_height_mm is None
    ):
        raise ValidationFailedError(
            "a CUSTOM paper size requires both page_width_mm and page_height_mm"
        )
    template.updated_by = user_id
    await session.flush()
    after = {field: getattr(template, field) for field in before}
    return before, after


async def archive_template(
    session: AsyncSession,
    *,
    template: InvoiceTemplate,
    user_id: uuid.UUID | None = None,
) -> list[InvoiceTemplateAssignment]:
    """Retire a template. One lifecycle column, so this is ``status``, not a flag.

    Active assignments pointing at it are deactivated in the same transaction. Leaving
    them live would keep resolving a retired design; silently resolving a *different* one
    would be worse, because the operator configured this one on purpose.
    """
    assert_editable(template)
    template.status = "ARCHIVED"
    template.updated_by = user_id
    rules = await session.execute(
        select(InvoiceTemplateAssignment).where(
            InvoiceTemplateAssignment.template_id == template.id,
            InvoiceTemplateAssignment.is_active.is_(True),
        )
    )
    deactivated = list(rules.scalars().all())
    for rule in deactivated:
        rule.is_active = False
        rule.updated_by = user_id
    await session.flush()
    return deactivated
