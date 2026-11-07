#!/bin/bash
# Read-only diagnosis. Use the VM's existing service credentials without displaying them.
set -a
. /etc/kiscobooks/reports.env
set +a
cd /opt/kiscobooks/current/apis/reports
.venv/bin/python - <<'PY'
import asyncio
import json
import os
import uuid
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from billing_platform.db import tenant_scope
from reports.models.framework import ReportJob
from reports.models.core import ReportGeneration
from reports.tasks import native_execution
from reports.domain.reporting.profit_views import present
from reports.tasks.reference_source import load
from reports.tasks.report_catalog import catalog
from reporting_contract.contract import Manifest

async def main():
    engine = create_async_engine(os.environ['REPORTS_DATABASE_URL'], echo=False)
    company = uuid.UUID('01a1b41e-71fa-7608-9bc6-b5b0b29f5612')
    # Administrative discovery bounded to the company observed in the failing request.
    async with engine.connect() as connection:
        tenant = await connection.scalar(select(ReportJob.__table__.c.tenant_id).where(ReportJob.__table__.c.company_id == company).limit(1))
    with tenant_scope(tenant):
        async with async_sessionmaker(engine)() as db:
            rows = await db.scalars(select(ReportJob).where(ReportJob.company_id == company).order_by(ReportJob.created_at.desc()).limit(8))
            for row in rows:
                print(json.dumps({'id': str(row.id), 'generation_id': str(row.generation_id), 'code': row.definition.get('code'), 'version': row.definition.get('version'), 'parameters': row.parameters, 'status': row.status, 'failure_code': row.failure_code, 'created_at': str(row.created_at)}, default=str))
            target = await db.scalar(select(ReportJob).where(ReportJob.company_id == company, ReportJob.id == uuid.UUID('01a1b443-f777-7035-94c1-81f20a574364')))
            generation = await db.scalar(select(ReportGeneration).where(ReportGeneration.company_id == company, ReportGeneration.id == target.generation_id))
            manifest = Manifest.model_validate(generation.manifest)
            print('SOURCE', json.dumps({'status': generation.status, 'coverage_start': str(manifest.control.coverage_start)}, default=str))
            settings = SimpleNamespace(native_queries_enabled=os.environ.get('REPORTS_NATIVE_QUERIES_ENABLED', '').lower() in ('1', 'true', 'yes'))
            native = await native_execution.enabled(db, settings, company, generation.id, 'PROFIT_LOSS')
            print('NATIVE', native)
            stage = 'CALCULATE'
            try:
                if native:
                    values, evidence = await native_execution.calculate(db, target, 100000)
                else:
                    facts = await load(db, generation, 20000)
                    values, evidence = catalog().resolve('PROFIT_LOSS', 6).handler.execute(facts, generation.id, target.parameters, manifest.control)
                stage = 'PRESENT'
                values, summary = present(values, comparison=False, show_zero=False)
                print('READ_ONLY_CALCULATION_OK', len(values))
            except Exception as error:
                print('READ_ONLY_CALCULATION_ERROR', stage, type(error).__name__, str(error))
            corrected = SimpleNamespace(company_id=target.company_id, generation_id=target.generation_id, definition=target.definition, parameters={**target.parameters, 'date_from': str(manifest.control.coverage_start)}, options=target.options)
            try:
                if native:
                    values, evidence = await native_execution.calculate(db, corrected, 100000)
                else:
                    facts = await load(db, generation, 20000)
                    values, evidence = catalog().resolve('PROFIT_LOSS', 6).handler.execute(facts, generation.id, corrected.parameters, manifest.control)
                values, summary = present(values, comparison=False, show_zero=False)
                print('COVERAGE_DATE_READ_ONLY_CALCULATION_OK', len(values))
            except Exception as error:
                print('COVERAGE_DATE_READ_ONLY_CALCULATION_ERROR', type(error).__name__, str(error))
    await engine.dispose()

try:
    asyncio.run(main())
except Exception as error:
    print('DIAGNOSTIC_ERROR', type(error).__name__)
    raise SystemExit(1)
PY
