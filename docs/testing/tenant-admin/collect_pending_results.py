"""Rebuild current CSV evidence without editing historical acceptance records."""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIVE = ROOT / ".test_artifacts/tenant-admin-20261029/live"
DESTINATION = ROOT / "docs/tenant-admin-fixes-after-6-results-2026-10-30.csv"
COLUMNS = ["case_id", "backlog_item", "category", "area", "company", "preconditions",
           "steps", "expected", "actual", "status", "execution_level", "evidence", "started_utc"]


def main() -> None:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    ledgers = [("pending-7", "7"), ("pending-7-recheck", "7"), ("pending-7-stock", "7"),
               ("pending-8-refresh", "8"), ("permanent-role-authority", "9"),
               ("pending-9", "9"), ("items-filter-layout", "17"),
               ("master-filter-layout", "17"), ("master-filter-layout-recheck", "17"),
               ("master-filter-responsive", "17"), ("pending-12", "12")]
    ledgers.insert(-1, ("master-filter-responsive-final", "17"))
    ledgers.insert(-1, ("master-filter-responsive-recheck", "17"))
    ledgers.append(("pending-10-11", "10"))
    ledgers.append(("pending-12-recheck", "12"))
    ledgers.extend([("permanent-opening-authority", "8"), ("pending-8-opening-access", "8"), ("pending-8-opening-preview", "8")])
    ledgers.append(("pending-14", "14"))
    ledgers.extend((name, "13") for name in ["pending-13", "pending-13-recheck", "pending-13-final", "pending-13-rounded", "pending-13-rounded-recheck", "pending-13-services", "pending-13-services-recheck", "pending-13-distribution", "pending-13-distribution-recheck"])
    ledgers.extend((name, "17") for name in ["pending-17-controls", "pending-17-controls-recheck", "pending-17-typed-submit", "pending-17-typed-submit-recheck"])
    for name, item in ledgers:
        source = LIVE / (name + "-results.json")
        if not source.exists():
            continue
        for result in json.loads(source.read_text(encoding="utf-8"))["results"]:
            row = {column: str(result.get(column, "")) for column in COLUMNS}
            row.update(case_id=result["id"], backlog_item=("11" if result["id"].startswith("P11-") else "10" if result["id"].startswith("P10-") else item), category="VERIFICATION",
                       evidence=result.get("evidence") or source.relative_to(ROOT).as_posix())
            rows[(row["case_id"], row["company"])] = row
    suites = [("pending-8-native/results.xml", "8", "NATIVE_MYSQL_MODEL_SCHEMA"),
              ("pending-8-audit-full.xml", "8", "NATIVE_MYSQL_AND_REAL_BROKER_SUITE"),
              ("pending-9-native/results.xml", "9", "NATIVE_MYSQL_MODEL_SCHEMA"),
              ("permanent-authority-identity.xml", "9", "API_FIXTURE_SUITE"),
              ("items-filter-current.xml", "17", "COMPONENT_FIXTURE_SUITE"),
              ("master-css-geometry.xml", "17", "BROWSER_GEOMETRY_AND_COMPONENT_SUITE")]
    suites.append(("pending-16-notification.xml", "16", "PROVIDER_AND_DELIVERY_FIXTURE_SUITE"))
    suites.extend([
        ("permanent-opening-identity.xml", "8", "API_FIXTURE_SUITE"),
        ("permanent-opening-page.xml", "8", "COMPONENT_FIXTURE_SUITE"),
        ("permanent-opening-native/results.xml", "8", "NATIVE_MYSQL_MODEL_SCHEMA"),
        ("pending-14-api.xml", "14", "API_FIXTURE_SUITE"),
        ("pending-14-native/results.xml", "14", "NATIVE_MYSQL_MODEL_SCHEMA"),
        ("pending-14-console.xml", "14", "COMPONENT_FIXTURE_SUITE"),
        ("pending-13-native/results.xml", "13", "NATIVE_MYSQL_MODEL_SCHEMA"),
        ("pending-13-console.xml", "13", "COMPONENT_FIXTURE_SUITE"),
        ("pending-12-native/results.xml", "12", "NATIVE_MYSQL_MODEL_SCHEMA"),
        ("pending-15-native/results.xml", "15", "NATIVE_MYSQL_MODEL_SCHEMA"),
        ("pending-17-report-console.xml", "17", "COMPONENT_FIXTURE_SUITE"),
    ])
    for name, item, level in suites:
        source = LIVE / name
        if not source.exists():
            continue
        tree = ET.parse(source)
        for index, case in enumerate(tree.iter("testcase"), 1):
            status = "FAIL" if case.find("failure") is not None or case.find("error") is not None else "SKIP" if case.find("skipped") is not None else "PASS"
            row = dict.fromkeys(COLUMNS, "")
            suite_name = source.relative_to(LIVE).with_suffix("").as_posix().replace("/", "-")
            row.update(case_id=f"SUITE-{item}-{suite_name}-{index}", backlog_item=item,
                       category="VERIFICATION", area=case.get("classname", ""),
                       preconditions="Use the documented service/component test environment; native suites require the dedicated disposable MySQL schema, not an application database",
                       steps=case.get("name", ""), expected="Assertions pass",
                       actual=f"Test outcome {status}; elapsed {case.get('time', '')} seconds",
                       status=status, execution_level=level, evidence=source.relative_to(ROOT).as_posix())
            rows[(row["case_id"], "")] = row
    notices = [
        ("BUG-REPORT-SOURCE-GENERATION", "9", "BUG", "Accounting setup-only changes gave snapshot/feed different generations", "FIXED", "Two regressions reproduced before fix; 14 native feed/snapshot cases passed; live READY source and strict report execution verified"),
        ("BUG-ITEMS-FILTER-ALIGNMENT", "17", "BUG", "Simple products mixed label-free search and stacked filters", "FIXED", "Component and three live viewport regressions reproduced before using shared FilterBar"),
        ("BUG-SHARED-FILTER-LAYOUT", "17", "BUG", "Lookup/date/hint query layouts and narrow wrapping", "FIXED", "Shared CSS reviewed; 45 desktop destinations and 20 representative responsive cases pass after rechecks; four native browser geometry cases pass"),
        ("BUG-TENANT-ADMIN-OPENING-AUTHORITY", "8", "BUG", "Shipped tenant administrator lacked native opening management/posting/export permissions", "FIXED", "User-approved canonical policy and fixed seed applied through platform UI; seven grants added with existing assignments preserved; fresh seed/provisioning and live three-company authority verified"),
        ("BUG-REPORT-TYPED-PARAMETERS", "17", "BUG", "Native integer arrays were submitted as text; boolean/count controls used text inputs", "FIXED", "Regression failures reproduced; typed arrays/checkboxes/counts preserve decimal strings; native report controls and validation have separate live evidence"),
        ("BUG-REPORT-STOCK-GROUP-LOOKUP", "17", "BUG", "Inventory report group filter used the Accounting chart group resource", "FIXED", "Regression reproduced; native Catalog item groups now used for inventory datasets; warehouse/batch and retained historical references are scoped native choices"),
        ("FIXTURE-MONEY-CLOSE-RACE", "12", "TEST_FIXTURE", "Money close-race fixture had an unfinished financial opening", "CORRECTED", "Native execution was correctly refused; finalize the fixture's zero opening before the race. All 19 native money cases then passed; original XML retained"),
        ("GAP-PROVIDER-VM-LIFECYCLE", "8", "GAP", "VM reboot/suspend/cold provider lifecycle", "NOT_RUN", "Natural expiry and owned tunnel reconnect passed; VM lifecycle has not been exercised"),
        ("GAP-MONEY-POSTED-ACCEPTANCE", "12", "GAP", "Separate-actor ordinary money posting and nonzero reconciliation", "NOT_RUN", "Entry implementation and draft verification do not establish C1 activation evidence"),
        ("GAP-INVOICE-OWNER-ACCEPTANCE", "13", "GAP", "Selected statutory invoice scope and C2 completion", "PENDING", "Native account Purchase UI is implemented and retained drafts use explicit NON_GST synthetic expenses. Country/tax selection instruction recorded; statutory UI/legal issue and C2 activation remain separate. 19 existing native invoice cases passed"),
        ("GAP-LIVE-DASHBOARD", "14", "GAP", "Replace sample dashboard with a scoped live aggregate", "IMPLEMENTED", "Native verified-source overview and actual customer lookup implemented; six three-company UI/API checks pass; nonzero native fixture totals verified. Live posted invoice/money acceptance remains with C1/C2."),
        ("GAP-STOCK-OWNER-ACCEPTANCE", "15", "GAP", "Goods/stock/physical count adjustment and C3 completion", "PENDING", "User selected physical count with calculated difference. Native cutoff/locking/count effect remains a work package under D03/B25; all 31 existing native stock cases pass, which does not establish count execution or C3"),
        ("GAP-INVITATION-MAILBOX", "16", "GAP", "Actual controlled external invitation delivery", "NOT_CONFIGURED", "User confirmed no SMTP/provider or controlled recipient; future configuration must be supported"),
        ("GAP-BANK-REPORT-FIXTURES", "17", "GAP", "Bank reconciliation parameter/workflow acceptance", "NOT_RUN", "All 38 report control sets were checked in each company; nine bank-specific parameter cases lack native bank/statement/session fixtures. Catalogue control passes do not establish populated report calculations"),
        ("GAP-STOCK-REPORT-COVERAGE", "15", "GAP", "Complete native inventory source for stock report execution", "PENDING", "The retained READY financial snapshots lack complete inventory source coverage. Live typed UI arrays/booleans reach the owner, which correctly refuses stock job creation with 409. Stock source/reconciliation prerequisites remain required"),
    ]
    for identity, item, category, area, status, actual in notices:
        row = dict.fromkeys(COLUMNS, "")
        row.update(case_id=identity, backlog_item=item, category=category, area=area,
                   status=status, actual=actual, evidence="docs/tenant-admin-fixes-todo.md")
        rows[(identity, "")] = row
    with DESTINATION.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(rows.values(), key=lambda row: (int(row["backlog_item"]), row["case_id"], row["company"])))
    style_rows = [row for row in rows.values() if row["case_id"].startswith(("MASTER-FILTER-", "ITEMS-FILTER-"))]
    with (ROOT / "docs/master-filter-alignment-results-2026-10-30.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(style_rows, key=lambda row: row["case_id"]))
    print(f"Wrote {len(rows)} current evidence rows to {DESTINATION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
