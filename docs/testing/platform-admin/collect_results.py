"""Build an auditable CSV from the selected final JUnit reports, excluding retries."""

from __future__ import annotations

import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reports", nargs="+", type=Path, help="Explicit JUnit reports for a fix retest")
    args = parser.parse_args()
    files = args.reports or [
        *[
            args.evidence / f"{name}.xml"
            for name in (
                "identity",
                "console",
                "auth",
                "auth-server",
                "audit",
                "notification",
            )
        ],
        *sorted((args.evidence / "native-isolated").glob("*.xml")),
    ]
    if not args.reports and (args.evidence / "acceptance-final.xml").exists():
        files.append(args.evidence / "acceptance-final.xml")
    if not args.reports and (args.evidence / "auth-redis.xml").exists():
        files.append(args.evidence / "auth-redis.xml")
    rows = []
    for file in files:
        for test in ET.parse(file).getroot().iter("testcase"):
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
            if file.stem == "auth-redis" and status == "SKIP":
                continue  # The focused native recheck deselects the other original cases.
            message = (
                ""
                if issue is None
                else (
                    issue.get("message", "").splitlines()
                    or ["No reason supplied by test"]
                )[0][:700]
            )
            message = re.sub(r"Bearer\s+[^\s'\"]+", "Bearer [redacted]", message)
            message = re.sub(
                r"https?://[^\s'\"]+\?[^\s'\"]+", "[URL query redacted]", message
            )
            mode = "Isolated API/domain/component fixtures; external services may be mocked"
            if "native-isolated" in str(file):
                mode = "Native MySQL 9.6.0; fresh schema per isolated/shared-order scenario; provider not live"
            elif file.stem == "auth-redis":
                mode = (
                    "Native Redis on loopback DB 15; provider refresh response mocked"
                )
            rows.append(
                [
                    file.stem,
                    test.get("classname", ""),
                    test.get("name", ""),
                    status,
                    test.get("time", ""),
                    mode,
                    message,
                    file.as_posix(),
                ]
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "suite",
                "test_class_or_file",
                "test_case",
                "result",
                "duration_seconds",
                "execution_mode",
                "failure_or_skip_reason",
                "evidence",
            ]
        )
        writer.writerows(rows)
    print(
        json.dumps(
            {"total": len(rows), "counts": dict(Counter(row[3] for row in rows))}
        )
    )


if __name__ == "__main__":
    main()
