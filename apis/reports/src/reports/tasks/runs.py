"""Frozen financial statements and registers from reconciled owner facts."""

import csv
import hashlib
import io
import uuid

from billing_platform.errors import ConflictError
from reporting_contract.contract import Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reconcile import RULE_HASH, reconcile
from reports.domain.statements import RULE_VERSIONS, RULES, calculate
from reports.models import core as m
from reports.schemas.requests import RunRequest
from reports.tasks.common import audit, get
from reports.tasks.reference_source import LEGACY_FACT_LIMIT, load


async def definition(
    db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID, code: str = "SOURCE_RECONCILIATION"
) -> m.ReportDefinition:
    rule_hash = RULE_HASH if code == "SOURCE_RECONCILIATION" else RULES[code]
    version = 2 if code == "SOURCE_RECONCILIATION" else RULE_VERSIONS[code]
    row = await db.scalar(
        select(m.ReportDefinition).where(
            m.ReportDefinition.company_id == company,
            m.ReportDefinition.code == code,
            m.ReportDefinition.version == version,
        )
    )
    if row:
        if row.rule_hash != rule_hash:
            raise ConflictError("report definition version changed")
        return row
    row = m.ReportDefinition(
        tenant_id=tenant,
        company_id=company,
        code=code,
        version=version,
        rule_hash=rule_hash,
    )
    db.add(row)
    await db.flush()
    audit(db, tenant, company, row.id, "defined")
    return row


def spreadsheet(value: object) -> str:
    text = str(value)
    return (
        "'" + text
        if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n"))
        else text
    )


async def complete(db: AsyncSession, run: m.ReportRun) -> None:
    if run.status == "COMPLETE":
        return
    if run.status != "PENDING":
        raise ConflictError("report run cannot be processed")
    generation = await get(db, run.company_id, m.ReportGeneration, run.generation_id)
    defined = await get(db, run.company_id, m.ReportDefinition, run.definition_id)
    if (
        generation.status != "READY"
        or generation.manifest is None
        or defined.rule_hash
        != (RULE_HASH if defined.code == "SOURCE_RECONCILIATION" else RULES.get(defined.code))
    ):
        raise ConflictError("report inputs or definition unavailable")
    manifest = Manifest.model_validate(generation.manifest)
    facts = await load(db, generation, LEGACY_FACT_LIMIT, bound_legacy=False)
    _, _, evidence = reconcile(facts, manifest.control)
    rows = [
        {"kind": "SOURCE_COUNT", "source": key, "count": value}
        for key, value in sorted(evidence["counts"].items())
    ]
    rows.extend(
        {"kind": "GL_CONTROL", "currency": currency, **totals}
        for currency, totals in sorted(evidence["base_totals"].items())
    )
    if defined.code != "SOURCE_RECONCILIATION":
        parameters = RunRequest.model_validate(run.parameters)
        assert manifest.control.coverage_start is not None
        rows, statement_evidence = calculate(facts, parameters, manifest.control.coverage_start)
        evidence |= statement_evidence
    for ordinal, value in enumerate(rows, 1):
        db.add(
            m.ReportRow(
                tenant_id=run.tenant_id,
                company_id=run.company_id,
                run_id=run.id,
                ordinal=ordinal,
                data=value,
            )
        )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    columns = sorted({key for row in rows for key in row})
    writer.writerow(columns)
    for row in rows:
        writer.writerow([spreadsheet(row.get(key, "")) for key in columns])
    body = output.getvalue()
    content_hash = hashlib.sha256(body.encode()).hexdigest()
    db.add(
        m.ReportArtifact(
            tenant_id=run.tenant_id,
            company_id=run.company_id,
            run_id=run.id,
            body=body,
            content_hash=content_hash,
        )
    )
    run.evidence = evidence | {
        "owner_manifest": generation.manifest,
        "generation_id": str(generation.id),
        "definition_id": str(defined.id),
        "permission_hash": run.permission_hash,
        "artifact_hash": content_hash,
        "statement_readiness": "NOT_A_FINANCIAL_STATEMENT"
        if defined.code == "SOURCE_RECONCILIATION"
        else "RECONCILED_OWNER_INPUT",
        "report_code": defined.code,
        "parameters": run.parameters,
    }
    run.status = "COMPLETE"
    run.row_version += 1
    audit(db, run.tenant_id, run.company_id, run.id, "completed")
