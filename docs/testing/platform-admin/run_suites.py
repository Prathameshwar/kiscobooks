"""Repeat the implemented platform-admin regression suites without changing app code.

Run from any directory using Python 3.12. Results are written under --output.
These suites use isolated fixtures; provider/browser verification is separate.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def suites():
    identity = ROOT / "apis/identity"
    console = ROOT / "mfes/apps/console"
    auth = ROOT / "mfes/apps/auth"
    backend = sorted(
        {
            *identity.glob("tests/test_platform*.py"),
            *identity.glob("tests/test_reference*.py"),
            *identity.glob("tests/test_account_review*.py"),
            *identity.glob("tests/test_administrator*.py"),
            identity / "tests/test_tenant_onboarding.py",
            identity / "tests/test_gap_impersonation.py",
            identity / "tests/test_impersonation_domain.py",
            identity / "tests/test_timezone_directory.py",
            identity / "tests/test_gateway_uri_scope.py",
            identity / "tests/test_gap_step_up.py",
            identity / "tests/test_gap_step_up_boundaries.py",
        }
    )
    frontend = sorted(
        {
            p
            for pattern in (
                "platform-*.test.*",
                "tenant-*.test.*",
                "reference-*.test.*",
                "notification-*.test.*",
                "timezone-ui.test.*",
                "account-review.test.*",
                "administration-navigation.test.*",
                "console-shell.test.*",
                "company-page-access.test.*",
                "administrator-password-recovery.test.*",
                "session-authority.test.*",
                "session-recovery.test.*",
            )
            for p in (console / "tests").glob(pattern)
        }
    )
    audit = ROOT / "apis/audit"
    notification = ROOT / "apis/notification"
    return {
        "identity": (
            identity,
            [
                str(identity / ".venv/Scripts/python.exe"),
                "-m",
                "pytest",
                "-q",
                *[str(p.relative_to(identity)) for p in backend],
            ],
        ),
        "console": (
            console,
            [
                "pnpm.cmd",
                "exec",
                "vitest",
                "run",
                "--maxWorkers=2",
                "--minWorkers=1",
                *[p.relative_to(console).as_posix() for p in frontend],
            ],
        ),
        "auth": (
            auth,
            ["pnpm.cmd", "exec", "vitest", "run", "--maxWorkers=2", "--minWorkers=1"],
        ),
        "auth-server": (
            auth,
            [
                "pnpm.cmd",
                "exec",
                "vitest",
                "run",
                "--config",
                "vitest.server.config.ts",
                "--maxWorkers=2",
                "--minWorkers=1",
            ],
        ),
        "audit": (
            audit,
            [
                str(audit / ".venv/Scripts/python.exe"),
                "-m",
                "pytest",
                "-q",
                "tests/test_platform_events.py",
                "tests/test_platform_pricing_events.py",
                "tests/test_read_boundaries.py",
                "tests/test_authenticated_delivery.py",
            ],
        ),
        "notification": (
            notification,
            [
                str(notification / ".venv/Scripts/python.exe"),
                "-m",
                "pytest",
                "-q",
                "tests/test_platform_delivery.py",
                "tests/test_management.py",
                "tests/test_configuration_ownership.py",
                "tests/test_configuration_lifecycle.py",
                "tests/test_security.py",
                "tests/test_native_provider_security.py",
            ],
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["all", *suites()], default="all")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / ".test_artifacts/platform-admin"
        / dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    failed = False
    for name, (cwd, command) in suites().items():
        if args.suite not in ("all", name):
            continue
        report = output / f"{name}.xml"
        command += (
            [f"--junitxml={report}"]
            if "pytest" in command
            else ["--reporter=default", "--reporter=junit", f"--outputFile={report}"]
        )
        print(f"Running {name}; log: {output / (name + '.log')}", flush=True)
        with (output / f"{name}.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=False
            )
        failed |= completed.returncode != 0
        print(f"{name}: exit {completed.returncode}", flush=True)
        if not report.exists():
            results.append(
                [
                    name,
                    "",
                    "",
                    "ERROR",
                    "No XML produced; see log",
                    str(output / f"{name}.log"),
                ]
            )
            continue
        for test in ET.parse(report).getroot().iter("testcase"):
            issue = next(
                (
                    test.find(tag)
                    for tag in ("failure", "error", "skipped")
                    if test.find(tag) is not None
                ),
                None,
            )
            status = (
                "PASS"
                if issue is None
                else {"failure": "FAIL", "error": "ERROR", "skipped": "SKIP"}[issue.tag]
            )
            results.append(
                [
                    name,
                    test.get("classname", ""),
                    test.get("name", ""),
                    status,
                    "" if issue is None else issue.get("message", ""),
                    str(report),
                ]
            )
    with (output / f"results-{args.suite}.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "suite",
                "test_class_or_file",
                "test_case",
                "result",
                "message",
                "evidence",
            ]
        )
        writer.writerows(results)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
