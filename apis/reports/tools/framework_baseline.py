"""Measure the legacy calculation path on a reproducible synthetic fixture.

Run from apis/reports: python -m tools.framework_baseline --transactions 1000
This is a domain baseline, not an end-to-end/native database capacity claim.
"""

import argparse
import importlib.metadata
import json
import os
import platform
import time
import tracemalloc
from pathlib import Path

from billing_platform.idempotency import canonical_json

from reports.domain.reconcile import reconcile
from reports.domain.statements import CODES, calculate
from reports.schemas.requests import RunRequest
from tools.framework_data import BEGIN, END, facts, identity, manifest


def measure(transactions: int) -> dict[str, object]:
    if 3 * transactions + 33 > 100_000:
        raise ValueError("legacy baseline must fit the current 100000-fact limit")
    source = manifest(
        transactions, tenant=identity(20), company=identity(21), snapshot=identity(22)
    )
    tracemalloc.start()
    started = time.perf_counter()
    rows = list(facts(transactions))
    loaded = time.perf_counter()
    _lines, _totals, controls = reconcile(rows, source.control)
    verified = time.perf_counter()
    result, evidence = calculate(
        rows,
        RunRequest(
            code="TRIAL_BALANCE",
            generation_id=identity(23),
            date_from=BEGIN,
            date_to=END,
        ),
        BEGIN,
    )
    finished = time.perf_counter()
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "kind": "legacy_domain_baseline",
        "business_transactions": transactions,
        "journal_lines": transactions * 2,
        "source_facts": len(rows),
        "wire_bytes": sum(len(canonical_json(row.model_dump(mode="json"))) + 1 for row in rows),
        "fact_hash": source.facts_hash,
        "fixture_version": 1,
        "load_seconds": loaded - started,
        "reconcile_seconds": verified - loaded,
        "calculation_seconds": finished - verified,
        "total_seconds": finished - started,
        "python_allocation_peak_bytes": peak,
        "result_rows": len(result),
        "balanced": result[-1]["difference"] == "0.0000",
        "controls": controls,
        "evidence": evidence,
        "implemented_codes": ["SOURCE_RECONCILIATION", *CODES],
        "environment": {
            "python": platform.python_version(),
            "os": platform.system(),
            "cpu_count": os.cpu_count(),
            "sqlalchemy": importlib.metadata.version("sqlalchemy"),
            "pydantic": importlib.metadata.version("pydantic"),
        },
        "limitations": ["tracemalloc is not RSS", "no database, queue, API or owner write fence"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = measure(args.transactions)
    body = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body + "\n", encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
