"""B45 evidence completeness gate; it cannot substitute for native acceptance."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from billing_platform.errors import ValidationFailedError

from vouchers.domain.registry import KINDS

_BATCH = re.compile(r"^B(?:0[1-9]|[1-3][0-9]|4[0-5])$")
_ROW = re.compile(r"^\|\s*(B\d{2})\s*\|")
_DEPENDENCY = re.compile(r"\bB\d{2}\b")
CASE_COUNTS = {
    "AC": 28,
    "RPT": 20,
    "INV": 24,
    "FY": 24,
    "BAL": 20,
    "STK": 20,
    "CAL": 28,
    "VCF": 24,
}
WORKSTREAMS = frozenset(
    {
        "CONTRACT_MIGRATION",
        "HISTORICAL_BACKFILL",
        "MONEY_TAX_BRIDGE",
        "STOCK_ORDER_JOB_BRIDGE",
        "REPORT_REBUILD",
        "OPTIONAL_BANKING",
        "FISCAL_RECOVERY_LOAD",
        "SECURITY_CLIENT_OPERATIONS",
    }
)
SCOPE_FIELDS = frozenset(
    {
        "tenant_companies",
        "financial_years",
        "service_versions",
        "migration_heads",
        "selected_features",
        "catalog_release_versions",
        "configuration_versions",
        "valuation_methods",
        "tax_rule_versions",
        "report_mapping_versions",
        "integration_versions",
        "owner_barrier",
    }
)


@dataclass(frozen=True, slots=True)
class Evidence:
    result: Literal["PASS", "NOT_APPLICABLE", "PENDING"]
    artifact: str = ""
    reviewer: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    scope: dict[str, str] = field(default_factory=dict)
    kinds: dict[str, Evidence] = field(default_factory=dict)
    cases: dict[str, Evidence] = field(default_factory=dict)
    workstreams: dict[str, Evidence] = field(default_factory=dict)
    reservation_selected: bool = False


def batch_statuses(tracker: str) -> dict[str, str]:
    """Read the current 45-row batch register, refusing duplicate or missing rows."""
    found: dict[str, str] = {}
    dependencies: dict[str, tuple[str, ...]] = {}
    conditional_reservation: set[str] = set()
    for line in tracker.splitlines():
        match = _ROW.match(line)
        if not match:
            continue
        batch = match.group(1)
        if not _BATCH.fullmatch(batch) or batch in found:
            raise ValidationFailedError("batch tracker has duplicate or invalid batch rows")
        columns = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(columns) != 7 or columns[0] != batch:
            raise ValidationFailedError("batch tracker row has an invalid column shape")
        dependencies[batch] = tuple(_DEPENDENCY.findall(columns[4]))
        if batch == "B32" and "B31 if reservation views enabled" in columns[4]:
            conditional_reservation.add(batch)
        found[batch] = columns[-1]
    expected = {f"B{number:02d}" for number in range(1, 46)}
    if set(found) != expected:
        raise ValidationFailedError("batch tracker does not contain exactly B01-B45")
    for batch, required in dependencies.items():
        for predecessor in required:
            if predecessor not in found or int(predecessor[1:]) >= int(batch[1:]):
                raise ValidationFailedError("batch tracker has an invalid prerequisite")
            if batch in conditional_reservation and predecessor == "B31":
                continue
            if found[batch] == "VERIFIED" and found[predecessor] != "VERIFIED":
                raise ValidationFailedError("verified batch has an incomplete prerequisite")
    return found


def required_cases(*, reservation_selected: bool) -> frozenset[str]:
    cases = {
        f"{prefix}{number:02d}"
        for prefix, count in CASE_COUNTS.items()
        for number in range(1, count + 1)
    }
    cases.update(f"T{number}" for number in range(5))
    if not reservation_selected:
        cases.remove("AC21")
    return frozenset(cases)


def _acceptable(evidence: Evidence | None, *, allow_na: bool) -> bool:
    if evidence is None or not evidence.reviewer.strip():
        return False
    if evidence.result == "PASS":
        return bool(evidence.artifact.strip())
    return allow_na and evidence.result == "NOT_APPLICABLE" and bool(evidence.reason.strip())


def evaluate(statuses: dict[str, str], manifest: ReleaseManifest) -> tuple[str, ...]:
    """List every missing prerequisite; an empty list is only evidence-complete."""
    required_batches = {f"B{number:02d}" for number in range(1, 45)}
    if not manifest.reservation_selected:
        required_batches.remove("B31")
    problems = [
        f"{batch}: batch not VERIFIED"
        for batch in sorted(required_batches)
        if statuses.get(batch) != "VERIFIED"
    ]
    problems.extend(
        f"{name}: frozen scope missing"
        for name in sorted(SCOPE_FIELDS)
        if not manifest.scope.get(name, "").strip()
    )
    problems.extend(
        f"{kind.code}: kind evidence missing"
        for kind in KINDS
        if not _acceptable(manifest.kinds.get(kind.code), allow_na=False)
    )
    for case in sorted(required_cases(reservation_selected=manifest.reservation_selected)):
        # AC cases are the selected capability acceptance contract; applicability
        # elsewhere needs an explicit reviewer and reason, never an absent row.
        if not _acceptable(manifest.cases.get(case), allow_na=not case.startswith("AC")):
            problems.append(f"{case}: case evidence missing")
    problems.extend(
        f"{name}: workstream evidence missing"
        for name in sorted(WORKSTREAMS)
        if not _acceptable(manifest.workstreams.get(name), allow_na=False)
    )
    return tuple(problems)


def tracker_file_statuses(path: Path) -> dict[str, str]:
    return batch_statuses(path.read_text(encoding="utf-8"))


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationFailedError(f"duplicate evidence field: {key}")
        result[key] = value
    return result


def _evidence_map(value: object, name: str) -> dict[str, Evidence]:
    if not isinstance(value, dict):
        raise ValidationFailedError(f"{name} must be an object")
    result: dict[str, Evidence] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not isinstance(raw, dict):
            raise ValidationFailedError(f"{name} has an invalid evidence row")
        if set(raw) != {"result", "artifact", "reviewer", "reason"}:
            raise ValidationFailedError(f"{name}.{key} has invalid evidence fields")
        if any(not isinstance(item, str) for item in raw.values()):
            raise ValidationFailedError(f"{name}.{key} values must be strings")
        if raw["result"] not in {"PASS", "NOT_APPLICABLE", "PENDING"}:
            raise ValidationFailedError(f"{name}.{key} has invalid result")
        result[key] = Evidence(**raw)
    return result


def load_manifest(source: str) -> ReleaseManifest:
    """Parse a reviewed evidence file without tolerating silent omissions/typos."""
    try:
        raw = json.loads(source, object_pairs_hook=_unique_pairs)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValidationFailedError("invalid release evidence JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "reservation_selected",
        "scope",
        "kinds",
        "cases",
        "workstreams",
    }:
        raise ValidationFailedError("release evidence has invalid top-level fields")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValidationFailedError("unsupported release evidence schema version")
    if type(raw["reservation_selected"]) is not bool:
        raise ValidationFailedError("reservation_selected must be boolean")
    scope = raw["scope"]
    if not isinstance(scope, dict) or set(scope) != SCOPE_FIELDS:
        raise ValidationFailedError("release evidence has invalid scope fields")
    if any(not isinstance(value, str) for value in scope.values()):
        raise ValidationFailedError("release evidence scope values must be strings")
    kinds = _evidence_map(raw["kinds"], "kinds")
    cases = _evidence_map(raw["cases"], "cases")
    workstreams = _evidence_map(raw["workstreams"], "workstreams")
    if set(kinds) - {kind.code for kind in KINDS}:
        raise ValidationFailedError("release evidence has unknown voucher kinds")
    if set(cases) - required_cases(reservation_selected=True):
        raise ValidationFailedError("release evidence has unknown acceptance cases")
    if set(workstreams) - WORKSTREAMS:
        raise ValidationFailedError("release evidence has unknown workstreams")
    return ReleaseManifest(
        scope=scope,
        kinds=kinds,
        cases=cases,
        workstreams=workstreams,
        reservation_selected=raw["reservation_selected"],
    )
