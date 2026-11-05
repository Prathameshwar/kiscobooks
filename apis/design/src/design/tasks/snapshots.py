"""Render snapshots — the record of what was printed (docs/invoice-design.md §7).

Append-only, and validated against the template it claims: a snapshot naming a version
that does not belong to its template, or a template this company cannot see, would make
the one record meant to be trustworthy untrustworthy.
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.ids import uuid7
from sqlalchemy import ColumnElement, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from design.models.template import InvoiceRenderSnapshot
from design.schemas.snapshots import SnapshotRecordRequest
from design.tasks.templates import get_template
from design.tasks.versions import get_version

#: The artifact's object key, by output format. Derived here and never supplied.
_EXTENSIONS = {
    "PDF": "pdf",
    "HTML": "html",
    "PNG": "png",
    "ZPL": "zpl",
    "ESC_POS": "bin",
}


def artifact_path(
    *,
    prefix: str,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    output_format: str,
) -> str:
    """``<prefix>/renders/<tenant>/<company>/<snapshot>.<ext>`` — derived, never supplied."""
    return (
        f"{prefix}/renders/{tenant_id}/{company_id}/" f"{snapshot_id}.{_EXTENSIONS[output_format]}"
    )


async def record_snapshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    input_data: SnapshotRecordRequest,
    prefix: str,
    user_id: uuid.UUID | None = None,
) -> InvoiceRenderSnapshot:
    """Record one rendered artifact.

    An archived template is still a legitimate subject: a document printed last year was
    printed from the design that was live then, and the snapshot has to be able to say so.
    """
    template = await get_template(
        session,
        template_id=input_data.template_id,
        company_id=company_id,
        include_archived=True,
    )
    version = await get_version(
        session, version_id=input_data.template_version_id, template_id=template.id
    )
    snapshot_id = uuid7()
    snapshot = InvoiceRenderSnapshot(
        id=snapshot_id,
        tenant_id=tenant_id,
        company_id=company_id,
        voucher_id=input_data.voucher_id,
        voucher_revision_id=input_data.voucher_revision_id,
        template_id=template.id,
        template_version_id=version.id,
        output_format=input_data.output_format,
        render_channel=input_data.render_channel,
        storage_path=artifact_path(
            prefix=prefix,
            tenant_id=tenant_id,
            company_id=company_id,
            snapshot_id=snapshot_id,
            output_format=input_data.output_format,
        ),
        checksum_sha256=input_data.checksum_sha256,
        file_size_bytes=input_data.file_size_bytes,
        render_duration_ms=input_data.render_duration_ms,
        rendered_by=user_id,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def list_snapshots(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    limit: int,
    voucher_id: uuid.UUID | None = None,
    keyset: ColumnElement[bool] | None = None,
) -> list[InvoiceRenderSnapshot]:
    """Print history for this company, or for one document, most recent first."""
    conditions: list[Any] = [InvoiceRenderSnapshot.company_id == company_id]
    if voucher_id is not None:
        conditions.append(InvoiceRenderSnapshot.voucher_id == voucher_id)
    if keyset is not None:
        conditions.append(keyset)
    result = await session.execute(
        select(InvoiceRenderSnapshot)
        .where(*conditions)
        .order_by(desc(InvoiceRenderSnapshot.rendered_at), desc(InvoiceRenderSnapshot.id))
        .limit(limit + 1)
    )
    return list(result.scalars().all())
