"""Atomic definition adoption: validate current values, then rebuild derived indexes/claims."""

import uuid
from typing import Any

from billing_platform.custom_fields import CustomDefinition, scalar_value, validate_definitions
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.tasks import custom_fields
from vouchers.tasks.common import audit, expected, get
from vouchers.tasks.documents import content


async def adopt(
    db: AsyncSession, current: Access, object_id: uuid.UUID, version: int
) -> m.VoucherFieldAdoption:
    row = await get(db, current, m.VoucherFieldAdoption, object_id, lock=True)
    expected(row, version)
    projection = await get(db, current, m.VoucherDefinitionProjection, row.definition_id, lock=True)
    if row.status != "PENDING" or row.source_version <= projection.source_version:
        raise ConflictError("adoption is no longer pending")
    old = CustomDefinition.model_validate(projection.definition)
    candidate = CustomDefinition.model_validate(row.definition)
    if old.data_type != candidate.data_type or old.sequence_config != candidate.sequence_config:
        raise ConflictError("used field type and numbering identity cannot change")
    if candidate.option_source_key != old.option_source_key:
        raise ConflictError("used dynamic option source cannot change")
    # One fence protects validation, claims, indexes and publication. Bounded C0 adoption
    # rejects a large job before mutating; later bulk tools must use a resumable shadow generation.
    revisions = list(
        await db.scalars(
            select(m.VoucherRevision)
            .join(
                m.Voucher,
                (m.Voucher.id == m.VoucherRevision.voucher_id)
                & (m.Voucher.current_revision == m.VoucherRevision.revision_number),
            )
            .where(m.VoucherRevision.company_id == current.context.company_id)
            .limit(1001)
        )
    )
    if len(revisions) > 1000:
        raise ConflictError("adoption exceeds atomic review limit; requires a bulk migration")
    pending: list[tuple[m.VoucherRevision, uuid.UUID, dict[str, Any], dict[str, Any]]] = []
    for revision in revisions:
        raw = await content(db, current, revision)
        entries = (
            [(revision.voucher_id, raw)]
            if projection.entity_type == "vouchers.voucher"
            else [
                (uuid.uuid5(revision.voucher_id, line["line_key"]), line["item"])
                for line in raw["lines"]
            ]
        )
        for entity_id, native in entries:
            data = native.get("custom_fields", {})
            value = data.get(candidate.key)
            if candidate.is_active and candidate.validation.required and value in (None, "", []):
                raise ConflictError("current values do not satisfy proposed definition")
            if value is not None:
                try:
                    validated = scalar_value(
                        candidate, value, currencies=frozenset({current.context.base_currency})
                    )
                except ValueError as exc:
                    raise ValidationFailedError(
                        "current values do not satisfy proposed definition"
                    ) from exc
                if validated != value:
                    raise ConflictError("adoption would reinterpret retained values")
            pending.append((revision, entity_id, data, native))
    definitions = list(
        await db.scalars(
            select(m.VoucherDefinitionProjection)
            .where(
                m.VoucherDefinitionProjection.company_id == current.context.company_id,
                m.VoucherDefinitionProjection.entity_type == projection.entity_type,
            )
            .limit(129)
        )
    )
    validate_definitions(
        tuple(
            candidate
            if entry.id == projection.id
            else CustomDefinition.model_validate(entry.definition)
            for entry in definitions
        ),
        native_fields=frozenset(
            {"document_date", "currency", "mode", "narration"}
            if projection.entity_type == "vouchers.voucher"
            else {"actual_quantity", "billed_quantity", "item_id", "unit_id"}
        ),
        option_sources=frozenset({"items", "parties", "voucher_types"}),
    )
    projection.definition = row.definition
    projection.presentation = row.presentation
    projection.content_hash = row.content_hash
    projection.source_version = row.source_version
    projection.row_version += 1
    for revision, entity_id, data, native in pending:
        normalized, defs = await custom_fields.normalize(
            db,
            current,
            projection.entity_type,
            entity_id,
            data,
            data,
            native,
            allowed=None,
            day=revision.document_date,
            creating=False,
        )
        if normalized != data:
            raise ConflictError("adoption requires explicit content revisions")
        await custom_fields.indexes(
            db,
            current,
            projection.entity_type,
            entity_id,
            revision.voucher_id,
            revision.id,
            defs,
            data,
        )
    row.status = "APPLIED"
    row.row_version += 1
    audit(db, current, "definition", projection.id, "adopt")
    return row
