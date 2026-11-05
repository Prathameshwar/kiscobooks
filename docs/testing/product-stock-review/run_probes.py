"""Replay review diagnostics without editing application code or live data.

Run: apis/accounting/.venv/Scripts/python.exe docs/testing/product-stock-review/run_probes.py
Diagnostics assert observed defects; cases.csv records desired acceptance behavior.
"""

import argparse
import hashlib
import os
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def run(project, name, args, *, console=False):
    suffix = ".test.tsx" if console else ".py"
    target = (
        project / "tests" / ("test_product_stock_review_" + uuid.uuid4().hex + suffix)
    )
    content = (HERE / name).read_bytes()
    with target.open("xb") as out:
        out.write(content)
    try:
        if console:
            command = [
                "pnpm.cmd" if os.name == "nt" else "pnpm",
                "exec",
                "vitest",
                "run",
            ]
        else:
            interpreter = project / (
                ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
            )
            command = [str(interpreter), "-m", "pytest", "-q"]
        return subprocess.run(
            [*command, *args, str(target)], cwd=project, check=False
        ).returncode
    finally:
        if (
            target.exists()
            and hashlib.sha256(target.read_bytes()).digest()
            == hashlib.sha256(content).digest()
        ):
            target.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("accounting", "reports", "console"))
    selection = parser.parse_args().only
    (ROOT / ".test_artifacts").mkdir(exist_ok=True)
    results = []
    if selection in {None, "accounting"}:
        results.append(
            run(
                ROOT / "apis/accounting",
                "accounting_probes.py",
                [
                    "--junitxml="
                    + str(ROOT / ".test_artifacts/product-stock-review-probes.xml")
                ],
            )
        )
    if selection in {None, "reports"}:
        results.append(
            run(
                ROOT / "apis/reports",
                "report_probes.py",
                [
                    "--junitxml="
                    + str(
                        ROOT / ".test_artifacts/product-stock-review-report-probes.xml"
                    )
                ],
            )
        )
    if selection in {None, "console"}:
        results.append(
            run(
                ROOT / "mfes/apps/console",
                "console_probes.test.tsx",
                [
                    "--reporter=json",
                    "--outputFile="
                    + str(
                        ROOT
                        / ".test_artifacts/product-stock-review-console-probes.json"
                    ),
                ],
                console=True,
            )
        )
    raise SystemExit(int(any(results)))
