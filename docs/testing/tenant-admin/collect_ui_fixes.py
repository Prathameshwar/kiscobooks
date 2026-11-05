"""Collect the current UI-fix verdicts without rewriting the historical review."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / ".test_artifacts"
DOCS = ROOT / "docs"

# Implementation status and acceptance are separate: a local PASS is not live acceptance.
CHANGES = {
    "UI-B01": (
        "FIXED_LOCAL",
        "Responsive designer toolbar and single compact panel, Escape dismissal and focus return.",
        "invoice-designer-layout.browser.test.tsx; invoice-designer-panels.test.tsx",
        "designer",
    ),
    "UI-B02": (
        "FIXED_LOCAL",
        "Shared 2.25rem outer control height, native date alignment and lookup padding; multiple chips can grow.",
        "filter-bar-layout.browser.test.tsx; search-select*.test.tsx; select.test.tsx",
        "controls",
    ),
    "UI-B03": (
        "FIXED_LOCAL",
        "Shared financial/related fieldgroups, form grids and grouped actions.",
        "voucher-money.test.tsx; money-entry-form.test.tsx",
        "components",
    ),
    "UI-B04": (
        "FIXED_LOCAL",
        "ACCOUNTS mode hides item entry and clears local item lines when selected.",
        "money-entry-form.test.tsx; voucher-entry-stock.test.tsx",
        "components",
    ),
    "UI-B05": (
        "FIXED_LOCAL",
        "Saved voucher Back uses the scoped voucher directory.",
        "voucher-detail-page.test.tsx",
        "components",
    ),
    "UI-B06": (
        "FIXED_LOCAL",
        "Selected customer opens PARTY_LEDGER; reference is company-verified before submission.",
        "report-card-connection.test.tsx; report-workspace.test.tsx; report-references.test.tsx",
        "labels",
    ),
    "UI-B07": (
        "FIXED_LOCAL",
        "Preview uses company display precision/rounding plus explicit voucher currency; native decimals remain unchanged.",
        "voucher-workflow.test.tsx",
        "components",
    ),
    "UI-B08": (
        "FIXED_LOCAL",
        "Purchase errors associate with individual controls and focus the first invalid field; invalid capture never writes.",
        "purchase-validation.test.tsx; purchase-entry-contract.test.ts; purchase-entry-save.test.tsx",
        "components",
    ),
    "UI-B09": (
        "FIXED_LOCAL",
        "Transition arrow and issue separator render readable text.",
        "voucher-workflow.test.tsx",
        "components",
    ),
    "UI-B10": (
        "FIXED_LOCAL",
        "Failed Audit/Activity reads suppress empty count captions and retain error/retry.",
        "audit-events.test.tsx; activity-feed.test.tsx",
        "components",
    ),
    "UI-B11": (
        "FIXED_LOCAL",
        "Fixed security-exclusion chip omits the internal operator and remains unremovable.",
        "audit-events.test.tsx",
        "components",
    ),
    "UI-B12": (
        "FIXED_LOCAL",
        "Saved workflow actions use shared spacing and wrapping.",
        "voucher-workflow.test.tsx",
        "components",
    ),
    "UI-G01": (
        "PARTIAL_LOCAL",
        "Scoped directory and versioned money/untaxed Purchase reopen/edit. Purchase saves preserve unrelated parties/references and line/tax context evidence; uncertain saves replay exactly.",
        "voucher-directory.test.tsx; voucher-draft-edit.test.tsx; voucher-draft-pages.test.tsx",
        "drafts",
    ),
    "UI-G02": (
        "IMPLEMENTED_LOCAL",
        "Automatic verified saved capture summary with readable native fields, formatted values, revision/IDs and scoped current master labels.",
        "voucher-summary.test.tsx; voucher-workflow.test.tsx; voucher-reference-labels.test.ts",
        "drafts",
    ),
    "UI-G03": (
        "PARTIAL_LOCAL",
        "Source options explain native ledger coverage or unavailable coverage; stock completeness is explicitly not certified by financial READY.",
        "report-source-summary.test.tsx; report-workspace.test.tsx",
        "components",
    ),
    "UI-G04": (
        "IMPLEMENTED_LOCAL",
        "Report/export history shows formatted creation time and full identity; long labels wrap at phone width.",
        "report-workspace.test.tsx; review-layout.browser.test.tsx",
        "labels",
    ),
    "UI-G05": (
        "OPEN_OWNER_WORK",
        "Country/tax selection retained; existing entry remains the supported untaxed account profile.",
        "purchase-entry-contract.test.ts",
        None,
    ),
    "UI-G06": (
        "OPEN_OWNER_WORK",
        "Count cutoff and verified-cost/review policies recorded in the native owner plan and decision tracker; no count effect implemented.",
        "docs/tenant-admin-stock-entry-plan.md",
        None,
    ),
    "UI-G07": (
        "NOT_CONFIGURED",
        "Existing provider-ready invitation implementation retained; controlled provider/mailbox absent.",
        "docs/tenant-admin-fixes-todo.md",
        None,
    ),
    "UI-G08": (
        "IMPLEMENTED_LOCAL",
        "Selected report definitions, sources and history load automatically; retry retained and no automatic run creation.",
        "report-workspace.test.tsx; report-card-connection.test.tsx",
        "labels",
    ),
}
REMAINING = {
    "UI-G01": "Dedicated editing for goods/tax/Sales/stock/other native captures remains; the first editor pins dates/type and refuses unreadable or unsupported replacement shapes.",
    "UI-G03": "Current generation detail exposes ledger coverage, not full stock capability or source creation time. Native report admission retains stock compatibility authority.",
    "UI-G05": "Deliver native statutory/goods capture, owner posting/bridges and legal issue/artifacts under B15-B19/D05/C2; do not activate or substitute untaxed GST goods.",
    "UI-G06": "Deliver native count grain/API/migrations, protected cutoff history, concurrency fences, reviewed delta/cost owner execution and C3 acceptance. Both user policy questions are resolved.",
    "UI-G07": "Configure controlled transport and recipient; run actual delivery, retry/status and invitation acceptance. Previous fixture tests do not prove receipt.",
}
REPORTS = {
    "components": "ui-fixes-components-final.json",
    "controls": "ui-fixes-controls-final.json",
    "labels": "ui-fixes-label-review.json",
    "designer": "ui-fixes-designer-reports-green.json",
    "references": "ui-fixes-reference-labels-final.json",
    "drafts": "ui-fixes-draft-review-final.json",
}


def main() -> None:
    source = DOCS / "tenant-admin-ui-review-findings-2026-10-30.csv"
    with source.open(encoding="utf-8-sig", newline="") as stream:
        findings = list(csv.DictReader(stream))
    if {row["id"] for row in findings} != set(CHANGES) or len(findings) != 20:
        raise ValueError("Expected the original 20 unique UI findings")
    for filename in REPORTS.values():
        result = json.loads((ARTIFACTS / filename).read_text(encoding="utf-8"))
        if not result["success"] or result["numFailedTests"]:
            raise ValueError(f"Required local verification failed: {filename}")
    # The combined browser report also contains an initial helper-test cleanup
    # fixture failure. Inspect the six geometry assertions, not its overall verdict.
    browser = json.loads(
        (ARTIFACTS / "ui-fixes-final-browser-review.json").read_text(encoding="utf-8")
    )
    geometry = [
        case
        for suite in browser["testResults"]
        if suite["name"].endswith(
            (
                "invoice-designer-layout.browser.test.tsx",
                "review-layout.browser.test.tsx",
            )
        )
        for case in suite["assertionResults"]
    ]
    if len(geometry) != 6 or any(case["status"] != "passed" for case in geometry):
        raise ValueError("The six required responsive geometry assertions did not pass")
    pending_file = ARTIFACTS / "tenant-admin-20261029/live/ui-fixes-live-results.json"
    pending = json.loads(pending_file.read_text(encoding="utf-8"))
    if pending.get("executed") is not False or any(
        row["status"] != "NOT_RUN" for row in pending["results"]
    ):
        raise ValueError(
            "This dated collector expects explicitly unrun VM-dependent acceptance"
        )
    pending_cases = {row["id"]: row for row in pending["results"]}
    if set(pending_cases) != set(CHANGES) or len(pending["results"]) != 20:
        raise ValueError("Expected 20 unique reusable acceptance cases")
    rows = []
    for finding in findings:
        identity = finding["id"]
        status, change, tests, report = CHANGES[identity]
        evidence = "; ".join([".test_artifacts/" + REPORTS[report]] if report else [])
        if identity in {"UI-B01", "UI-G04"}:
            evidence += "; .test_artifacts/ui-fixes-final-browser-review.json (six selected geometry assertions PASS)"
        if identity == "UI-G02":
            evidence += "; .test_artifacts/" + REPORTS["references"]
        rows.append(
            {
                "id": identity,
                "category": finding["category"],
                "severity": finding["severity"],
                "complexity": finding["complexity"],
                "sequence": finding["suggested_sequence"],
                "area": finding["area"],
                "route": finding["route"],
                "finding": finding["finding"],
                "implementation_status": status,
                "change": change,
                "local_verification": "PASS_SUPPORTED_SLICE"
                if report
                else "NOT_ACCEPTED_AS_COMPLETE",
                "reusable_tests": tests,
                "local_evidence": evidence,
                "live_verification": "NOT_RUN_VM_OFF",
                "live_evidence": str(pending_file.relative_to(ROOT)).replace("\\", "/"),
                "remaining": REMAINING.get(
                    identity,
                    "Live UI/native recheck in the retained three-company tenant after VM services return.",
                ),
                "reusable_steps": pending_cases[identity]["steps"],
                "expected": pending_cases[identity]["expected"],
            }
        )
    destination = DOCS / "tenant-admin-ui-fixes-results-2026-10-30.csv"
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"Wrote {len(rows)} findings: 12 locally fixed bugs; 3 implemented and 2 partial UI gaps; 3 prerequisites. Live acceptance NOT_RUN."
    )


if __name__ == "__main__":
    main()
