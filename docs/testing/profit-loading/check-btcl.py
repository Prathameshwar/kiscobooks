"""Read-only BTCL report diagnosis using existing VM service credentials."""

import asyncio
import json
import os
import shlex
import uuid
from pathlib import Path
from types import SimpleNamespace

from billing_platform.db import tenant_scope
from reporting_contract.contract import Manifest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from reports.domain.reporting.profit_views import present
from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob
from reports.tasks import native_execution
from reports.tasks.reference_source import load
from reports.tasks.report_catalog import catalog


async def main():
    values = dict(line.split("=", 1) for line in Path("/etc/kiscobooks/identity.env").read_text().splitlines() if "=" in line and not line.startswith("#"))
    identity = create_async_engine(shlex.split(values["IDENTITY_DATABASE_URL"])[0], echo=False)
    async with identity.connect() as connection:
        companies = (await connection.execute(text("SELECT id, tenant_id, display_name FROM company WHERE LOWER(display_name)=:name OR LOWER(legal_name)=:name OR LOWER(trade_name)=:name LIMIT 5"), {"name": "btcl"})).all()
    await identity.dispose()
    engine = create_async_engine(os.environ["REPORTS_DATABASE_URL"], echo=False)
    for found in companies:
        company, tenant = uuid.UUID(bytes=found.id), uuid.UUID(bytes=found.tenant_id)
        print("COMPANY", found.display_name, str(company))
        with tenant_scope(tenant):
            async with async_sessionmaker(engine)() as db:
                job = await db.scalar(select(ReportJob).where(ReportJob.company_id == company, ReportJob.definition["code"].as_string() == "PROFIT_LOSS").order_by(ReportJob.created_at.desc()).limit(1))
                source = await db.scalar(select(ReportGeneration).where(ReportGeneration.company_id == company, ReportGeneration.status == "READY").order_by(ReportGeneration.created_at.desc()).limit(1))
                print("LATEST_RUN", json.dumps({"id": str(job.id), "status": job.status, "failure_code": job.failure_code, "parameters": job.parameters, "created_at": str(job.created_at)} if job else None))
                if source is None:
                    print("NO_READY_ACCOUNTING_SNAPSHOT")
                    continue
                manifest = Manifest.model_validate(source.manifest)
                print("LATEST_READY_SOURCE", json.dumps({"id": str(source.id), "coverage_start": str(manifest.control.coverage_start)}))
                if job is None:
                    continue
                native = await native_execution.enabled(db, SimpleNamespace(native_queries_enabled=os.environ.get("REPORTS_NATIVE_QUERIES_ENABLED", "").lower() in ("true", "1")), company, source.id, "PROFIT_LOSS")
                for start in dict.fromkeys([str(job.parameters["date_from"]), str(manifest.control.coverage_start)]):
                    trial = SimpleNamespace(company_id=company, generation_id=source.id, definition=job.definition, parameters={**job.parameters, "date_from": start}, options=job.options)
                    try:
                        if native:
                            rows, evidence = await native_execution.calculate(db, trial, 100000)
                        else:
                            facts = await load(db, source, 20000)
                            rows, evidence = catalog().resolve("PROFIT_LOSS", 6).handler.execute(facts, source.id, trial.parameters, manifest.control)
                        rows, summary = present(rows, comparison=(job.options or {}).get("view") == "comparison", show_zero=bool(job.parameters.get("show_zero")))
                        print("READ_ONLY_CALCULATION", start, "OK", len(rows))
                    except Exception as error:
                        print("READ_ONLY_CALCULATION", start, type(error).__name__, str(error))
    await engine.dispose()


try:
    asyncio.run(main())
except Exception as error:
    print("DIAGNOSTIC_ERROR", type(error).__name__)
    raise SystemExit(1)
