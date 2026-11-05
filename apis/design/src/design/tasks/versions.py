"""Domain rules for template versions (docs/invoice-design.md §5.1).

Two rules carry the weight here:

**A version is only ever reachable through its own template.** Every lookup takes the
template id and filters on it. Without that, a version id from another template — or
another company — could be read, and worse, *published* onto a template it does not
belong to, which would silently change what that company's documents look like
(CLAUDE.md §5.2).

**Numbering is allocated under a row lock** on the parent template, so two concurrent
saves cannot both claim version 4.
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, ValidationFailedError
from sqlalchemy import ColumnElement, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from design.models.template import InvoiceTemplate, InvoiceTemplateVersion
from design.schemas.versions import VersionCreate
from design.tasks.templates import assert_editable, layout_digest


async def list_versions(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    limit: int,
    keyset: ColumnElement[bool] | None = None,
) -> list[InvoiceTemplateVersion]:
    """The template's revision history, newest first."""
    conditions: list[Any] = [InvoiceTemplateVersion.template_id == template_id]
    if keyset is not None:
        conditions.append(keyset)
    result = await session.execute(
        select(InvoiceTemplateVersion)
        .where(*conditions)
        .order_by(desc(InvoiceTemplateVersion.created_at), desc(InvoiceTemplateVersion.id))
        .limit(limit + 1)
    )
    return list(result.scalars().all())


async def get_version(
    session: AsyncSession,
    *,
    version_id: uuid.UUID,
    template_id: uuid.UUID,
) -> InvoiceTemplateVersion:
    """One version **of this template**, or 404. The template predicate is the point."""
    result = await session.execute(
        select(InvoiceTemplateVersion).where(
            InvoiceTemplateVersion.id == version_id,
            InvoiceTemplateVersion.template_id == template_id,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise NotFoundError("template version not found")
    return version


async def create_version(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    template: InvoiceTemplate,
    input_data: VersionCreate,
    user_id: uuid.UUID | None = None,
) -> InvoiceTemplateVersion:
    """Append the next version of a template's canvas, numbering under a row lock."""
    assert_editable(template)
    await session.execute(
        select(InvoiceTemplate.id).where(InvoiceTemplate.id == template.id).with_for_update()
    )
    highest = await session.execute(
        select(func.max(InvoiceTemplateVersion.version_number)).where(
            InvoiceTemplateVersion.template_id == template.id
        )
    )
    version = InvoiceTemplateVersion(
        tenant_id=tenant_id,
        template_id=template.id,
        version_number=(highest.scalar() or 0) + 1,
        schema_version=input_data.layout_definition.schema_version,
        layout_definition=input_data.layout_definition.model_dump(mode="json"),
        layout_digest=layout_digest(input_data.layout_definition),
        change_summary=input_data.change_summary,
        created_by=user_id,
    )
    session.add(version)
    await session.flush()
    return version


async def publish_version(
    session: AsyncSession,
    *,
    template: InvoiceTemplate,
    version: InvoiceTemplateVersion,
    user_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID | None, uuid.UUID]:
    """Make this version the template's live layout.

    Returns the previous and new live version ids, which is what the audit row records:
    "documents printed from version 3 now print from version 4" is the auditable fact.
    Re-publishing the live version is a no-op rather than an error — the request's
    intent already holds — but it is still audited, because it is still an act.
    """
    assert_editable(template)
    if version.template_id != template.id:
        # Unreachable through the API, which resolves the version through its template.
        # Kept as a domain assertion so a future caller cannot reintroduce the hole.
        raise ValidationFailedError("a version can only be published on its own template")

    previous = template.current_version_id
    if version.published_at is None:
        version.published_at = utcnow()
        version.published_by = user_id
    template.current_version_id = version.id
    template.status = "PUBLISHED"
    template.updated_by = user_id
    await session.flush()
    return previous, version.id
