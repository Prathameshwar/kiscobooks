"""Deterministic escaped output pinned to revision, template and disclosure scope."""

import html
import json
import uuid
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.domain.configuration import digest
from vouchers.models import core as m
from vouchers.schemas.configuration import Policy
from vouchers.tasks.access import fingerprint
from vouchers.tasks.common import audit, expected, get, values
from vouchers.tasks.documents import detail, revision_for


async def prepare(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    version: int,
    template_revision_id: uuid.UUID | None,
) -> m.VoucherArtifact:
    voucher = await get(db, current, m.Voucher, voucher_id, lock=True)
    expected(voucher, version)
    revision = await revision_for(db, current, voucher)
    policy = Policy.model_validate(revision.configuration_evidence["policy"])
    template_revision_id = template_revision_id or policy.default_template_revision_id
    if template_revision_id is None or (
        policy.allowed_template_revision_ids is not None
        and template_revision_id not in policy.allowed_template_revision_ids
    ):
        raise ValidationFailedError("an allowed artifact template revision is required")
    template = await get(db, current, m.VoucherTemplateRevision, template_revision_id)
    parent = await get(db, current, m.VoucherTemplate, template.template_id)
    if parent.status != "ACTIVE":
        raise ConflictError("template is retired")
    scope = fingerprint(current)
    data = await detail(db, current, voucher.id)
    render_context = digest({"status": voucher.status, "issue_number": data.get("issue_number")})
    prior = await db.scalar(
        select(m.VoucherArtifact).where(
            m.VoucherArtifact.company_id == current.context.company_id,
            m.VoucherArtifact.revision_id == revision.id,
            m.VoucherArtifact.template_revision_id == template.id,
            m.VoucherArtifact.permission_hash == scope,
            m.VoucherArtifact.render_context_hash == render_context,
        )
    )
    if prior:
        return prior
    permitted = {key: data[key] for key in template.fields if key in data}
    evidence = {
        "title": template.title,
        "revision_id": str(revision.id),
        "template_hash": template.content_hash,
        "content": permitted,
        "status": data.get("status"),
        "issue_number": data.get("issue_number"),
    }
    artifact = m.VoucherArtifact(
        **values(current),
        revision_id=revision.id,
        template_revision_id=template.id,
        status="PENDING",
        permission_hash=scope,
        render_context_hash=render_context,
        body=json.dumps(evidence, sort_keys=True, separators=(",", ":")),
    )
    db.add(artifact)
    await db.flush()
    operation = m.VoucherOperation(
        **values(current),
        voucher_id=voucher.id,
        revision_id=revision.id,
        execution_id=artifact.id,
        purpose="ARTIFACT",
        status="PENDING",
        content_hash=revision.content_hash,
        configuration_hash=revision.configuration_hash,
        request_hash=digest(evidence),
        attempt_count=0,
    )
    db.add(operation)
    audit(db, current, "artifact", artifact.id, "create")
    return artifact


def render_evidence(evidence: dict[str, Any]) -> str:
    sections = "".join(
        "<section><h2>"
        + html.escape(key.replace("_", " ").title())
        + "</h2><pre>"
        + html.escape(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
            if isinstance(value, dict | list)
            else str(value)
        )
        + "</pre></section>"
        for key, value in evidence["content"].items()
    )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>'
        + html.escape(str(evidence["title"]))
        + "</title><body><h1>"
        + html.escape(str(evidence["title"]))
        + "</h1><p>Non-statutory document</p><p>"
        + html.escape(str(evidence.get("status") or ""))
        + " "
        + html.escape(str(evidence.get("issue_number") or ""))
        + "</p>"
        + sections
        + "</body></html>"
    )


async def render_pending(db: AsyncSession, artifact_id: uuid.UUID) -> m.VoucherArtifact:
    artifact = await db.scalar(
        select(m.VoucherArtifact).where(m.VoucherArtifact.id == artifact_id).with_for_update()
    )
    if artifact is None:
        raise ConflictError("artifact unavailable")
    if artifact.status == "READY":
        return artifact
    if artifact.status != "PENDING" or artifact.body is None:
        raise ConflictError("artifact cannot be rendered")
    operation = await db.scalar(
        select(m.VoucherOperation)
        .where(
            m.VoucherOperation.company_id == artifact.company_id,
            m.VoucherOperation.execution_id == artifact.id,
        )
        .with_for_update()
    )
    if operation is None:
        raise ConflictError("artifact operation unavailable")
    evidence = json.loads(artifact.body)
    if digest(evidence) != operation.request_hash:
        raise ConflictError("artifact request changed")
    artifact.body = render_evidence(evidence)
    artifact.content_hash = digest({"html": artifact.body})
    artifact.status = "READY"
    artifact.row_version += 1
    operation.status = "COMMITTED"
    operation.result = {"artifact_id": str(artifact.id), "content_hash": artifact.content_hash}
    operation.row_version += 1
    operation.attempt_count += 1
    from billing_platform.outbox import audit_payload, emit

    event = "vouchers.artifact.rendered"
    emit(
        db,
        aggregate_type="vouchers.artifact",
        aggregate_id=artifact.id,
        event_type=event,
        tenant_id=artifact.tenant_id,
        payload=audit_payload(
            action=event,
            entity_type="vouchers.artifact",
            entity_id=artifact.id,
            actor_user_id=None,
            company_id=artifact.company_id,
            category="system",
        )
        | {"actor_type": "system"},
    )
    return artifact
