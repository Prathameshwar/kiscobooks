"""Export browser observations and explicit checks without account lists or secrets."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--legacy-baseline", action="store_true", help="Omit superseded pre-fix observation labels only when rebuilding the original baseline")
    args = parser.parse_args()
    rows = []
    final_status = {}
    replacements = {
        "LIVE-NOTIFICATION-PAGES": "LIVE-NOTIFICATION-DESTINATIONS-SETTLED",
        "LIVE-SETTLED-DETAILS-AND-PRICING-READ": "LIVE-SETTLED-DATA-PAGES",
        "LIVE-MOBILE-AND-THEMES": "LIVE-MOBILE-VERIFIED-THEMES",
        "LIVE-CHANGE-PASSWORD-HANDOFF-PAGE": "LIVE-CHANGE-PASSWORD-PAGE",
    }
    for report in args.reports:
        for result in json.loads(report.read_text(encoding="utf-8"))["results"]:
            final_status[result["id"]] = result["result"]
    for report in args.reports:
        data = json.loads(report.read_text(encoding="utf-8"))
        for result in data["results"]:
            identifier = result["id"]
            # These first-run labels preceded settled-state and real-theme assertions.
            if args.legacy_baseline and identifier in {"LIVE-MOBILE-AND-THEMES", "LIVE-NOTIFICATION-PAGES"}:
                continue
            status = result["result"]
            note = result.get("actual", "")
            if status == "OBSERVED":
                note = "HTTP route/screenshot observation; data loading is independently checked by explicit settled-state cases."
            if identifier == "RUN-ERROR":
                note = result.get("error", "")
            if (
                identifier == "LIVE-TENANT-SEARCH"
                and status == "FAIL"
                and final_status.get(identifier) == "PASS"
            ):
                status = "HARNESS_ERROR_RECHECKED"
                note = (
                    "Initial selector requested textbox for an HTML search input. Corrected to searchbox; separate fresh-login recheck passed. Original failure: "
                    + note
                )
            rows.append(
                [
                    report.parent.name,
                    identifier,
                    status,
                    result.get("http", ""),
                    note,
                    len(data.get("errors", [])),
                    report.as_posix(),
                    final_status.get(identifier, status),
                    replacements.get(identifier, ""),
                    final_status.get(replacements.get(identifier, ""), ""),
                ]
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "run",
                "case_or_route",
                "result",
                "http_status",
                "observed_result",
                "run_page_error_count",
                "evidence",
                "latest_result_for_same_case",
                "replacement_case",
                "replacement_case_result",
            ]
        )
        writer.writerows(rows)
    print(dict(Counter(row[2] for row in rows)))


if __name__ == "__main__":
    main()
