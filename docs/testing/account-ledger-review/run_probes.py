"""Replay account opening/ledger review diagnostics in the existing disposable harnesses.

Run from the root with a local Python interpreter; optional --only accounting/reports/console.
UI checks assert fixed opening acceptance behavior; Reports diagnostics assert remaining
gaps. The Accounting probe verifies the current security policy.
"""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def run(project, name, console=False):
    suffix = ".test.tsx" if console else ".py"
    target = (
        project / "tests" / ("test_account_ledger_review_" + uuid.uuid4().hex + suffix)
    )
    content = (HERE / name).read_bytes()
    with target.open("xb") as stream:
        stream.write(content)
    try:
        if console:
            command = [
                "pnpm.cmd" if os.name == "nt" else "pnpm",
                "exec",
                "vitest",
                "run",
                "--reporter=json",
                "--outputFile="
                + str(
                    ROOT / ".test_artifacts/account-ledger-review-console-probes.json"
                ),
            ]
        else:
            interpreter = project / (
                ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
            )
            command = [
                str(interpreter),
                "-m",
                "pytest",
                "-q",
                "--junitxml="
                + str(
                    ROOT / (".test_artifacts/account-ledger-review-" + name + ".xml")
                ),
            ]
        environment = dict(
            os.environ,
            ACCOUNTING_TEST_DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REPORTS_TEST_DATABASE_URL="sqlite+aiosqlite:///:memory:",
        )
        return subprocess.run(
            [*command, str(target)], cwd=project, env=environment, check=False
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
    selected = parser.parse_args().only
    (ROOT / ".test_artifacts").mkdir(exist_ok=True)
    results = []
    if selected in {None, "accounting"}:
        results.append(run(ROOT / "apis/accounting", "accounting_probes.py"))
    if selected in {None, "reports"}:
        results.append(run(ROOT / "apis/reports", "report_probes.py"))
    if selected in {None, "console"}:
        results.append(
            run(ROOT / "mfes/apps/console", "console_probes.test.tsx", console=True)
        )
    raise SystemExit(int(any(results)))
