"""Replay review diagnostics without modifying application files or production data.

Run from the repository root with a local Python interpreter:
    python docs/testing/unit-stock-review/run_probes.py
    python docs/testing/unit-stock-review/run_probes.py --only console

High-finding probes assert the fixed behavior. Medium probes deliberately reproduce
still-open findings, as labelled in their test names. No live data is mutated.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARTIFACTS = ROOT / ".test_artifacts"


def executable(project: Path) -> Path:
    suffix = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return project / ".venv" / suffix


def temporary_suite(project: Path, source: str, suffix: str, command: list[str]) -> int:
    destination = project / "tests" / ("test_unit_stock_review_" + uuid.uuid4().hex + suffix)
    destination.resolve().relative_to((project / "tests").resolve())
    content = (HERE / source).read_bytes()
    checksum = hashlib.sha256(content).digest()
    with destination.open("xb") as stream:
        stream.write(content)
    try:
        return subprocess.run([*command, str(destination)], cwd=project, check=False).returncode
    finally:
        if destination.exists() and hashlib.sha256(destination.read_bytes()).digest() == checksum:
            destination.unlink()
        elif destination.exists():
            print(f"Preserved a concurrently changed diagnostic file: {destination}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("console", "catalog", "native"))
    args = parser.parse_args()
    ARTIFACTS.mkdir(exist_ok=True)
    outcomes = []
    if args.only in {None, "native"}:
        outcomes.append(subprocess.run(
            [str(executable(ROOT / "apis/catalog")), str(HERE / "native_probes.py")],
            cwd=ROOT, check=False,
        ).returncode)
    if args.only in {None, "catalog"}:
        project = ROOT / "apis/catalog"
        outcomes.append(temporary_suite(project, "catalog_probes.py", ".py", [
            str(executable(project)), "-m", "pytest", "-q", "--disable-warnings",
            "--junitxml=" + str(ARTIFACTS / "unit-stock-review-opening-query.xml"),
        ]))
    if args.only in {None, "console"}:
        project = ROOT / "mfes/apps/console"
        command = (["cmd", "/d", "/c", r".\node_modules\.bin\vitest.CMD"]
                   if os.name == "nt" else ["./node_modules/.bin/vitest"])
        outcomes.append(temporary_suite(project, "console_probes.test.tsx", ".test.tsx", [
            *command, "run", "--reporter=json",
            "--outputFile=" + str(ARTIFACTS / "unit-stock-review-probes.json"),
        ]))
    return int(any(outcomes))


if __name__ == "__main__":
    raise SystemExit(main())
