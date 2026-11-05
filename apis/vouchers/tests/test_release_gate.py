"""B45 must refuse omitted producers, kinds, cases and run workstreams."""

from pathlib import Path

import pytest
from billing_platform.errors import ValidationFailedError

from tools.verify_release import main, template
from vouchers.domain.registry import KINDS
from vouchers.domain.release_gate import (
    SCOPE_FIELDS,
    WORKSTREAMS,
    Evidence,
    ReleaseManifest,
    batch_statuses,
    evaluate,
    load_manifest,
    required_cases,
    tracker_file_statuses,
)

TRACKER = Path(__file__).resolve().parents[3] / "docs" / "voucher-delivery-tracker.md"


def complete(reservation_selected: bool = False) -> tuple[dict[str, str], ReleaseManifest]:
    passed = Evidence("PASS", artifact="native:test:sha256", reviewer="release-reviewer")
    statuses = {f"B{number:02d}": "VERIFIED" for number in range(1, 46)}
    manifest = ReleaseManifest(
        scope={field: "frozen:sha256" for field in SCOPE_FIELDS},
        kinds={kind.code: passed for kind in KINDS},
        cases={case: passed for case in required_cases(reservation_selected=reservation_selected)},
        workstreams={name: passed for name in WORKSTREAMS},
        reservation_selected=reservation_selected,
    )
    return statuses, manifest


def test_current_tracker_cannot_pass_b45():
    statuses = tracker_file_statuses(TRACKER)
    assert len(statuses) == 45
    assert statuses["B19"] == "PLANNED"
    problems = evaluate(statuses, ReleaseManifest())
    assert "B19: batch not VERIFIED" in problems
    assert "B42: batch not VERIFIED" in problems
    assert "JOB_WORK_OUT_ORDER: kind evidence missing" in problems
    assert "AC27: case evidence missing" in problems
    assert "REPORT_REBUILD: workstream evidence missing" in problems


def test_complete_manifest_and_conditional_reservation():
    statuses, manifest = complete()
    statuses["B31"] = "PLANNED"
    assert evaluate(statuses, manifest) == ()
    statuses, manifest = complete(reservation_selected=True)
    statuses["B31"] = "PLANNED"
    assert "B31: batch not VERIFIED" in evaluate(statuses, manifest)


def test_pending_or_unreviewed_not_applicable_does_not_pass():
    statuses, manifest = complete()
    manifest.cases["RPT01"] = Evidence("NOT_APPLICABLE", reviewer="reviewer")
    manifest.kinds["SALES"] = Evidence("PENDING", reviewer="reviewer")
    manifest.cases["AC27"] = Evidence("NOT_APPLICABLE", reason="claimed", reviewer="reviewer")
    problems = evaluate(statuses, manifest)
    assert "RPT01: case evidence missing" in problems
    assert "SALES: kind evidence missing" in problems
    assert "AC27: case evidence missing" in problems


def test_tracker_shape_and_duplicates_fail_closed():
    with pytest.raises(ValidationFailedError, match="exactly"):
        batch_statuses("| B01 | a | b | c | d | e | VERIFIED |")
    original = TRACKER.read_text(encoding="utf-8")
    row = next(line for line in original.splitlines() if line.startswith("| B01 |"))
    with pytest.raises(ValidationFailedError, match="duplicate"):
        batch_statuses(original + "\n" + row)


def test_tracker_rejects_false_completion_and_forward_prerequisites():
    original = TRACKER.read_text(encoding="utf-8")
    b16 = next(line for line in original.splitlines() if line.startswith("| B16 |"))
    with pytest.raises(ValidationFailedError, match="incomplete prerequisite"):
        batch_statuses(original.replace(b16, b16.replace("IN_PROGRESS", "VERIFIED")))

    b15 = next(line for line in original.splitlines() if line.startswith("| B15 |"))
    columns = b15.split("|")
    columns[5] = " B20 "
    with pytest.raises(ValidationFailedError, match="invalid prerequisite"):
        batch_statuses(original.replace(b15, "|".join(columns)))


def test_tracker_allows_unselected_reservation_before_order_reports():
    lines = TRACKER.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("| B"):
            continue
        columns = line.split("|")
        batch = columns[1].strip()
        if batch.startswith("B") and batch[1:].isdigit() and 15 <= int(batch[1:]) <= 32:
            if batch != "B31":
                columns[-2] = " VERIFIED "
                lines[index] = "|".join(columns)
    statuses = batch_statuses("\n".join(lines))
    assert statuses["B31"] == "PLANNED"
    assert statuses["B32"] == "VERIFIED"


def test_template_is_pending_and_strictly_parsed():
    source = template(reservation_selected=False)
    manifest = load_manifest(source)
    assert len(manifest.kinds) == len(KINDS)
    assert len(manifest.cases) == len(required_cases(reservation_selected=False))
    assert "AC21" not in manifest.cases
    assert "tenant_companies: frozen scope missing" in evaluate(complete()[0], manifest)
    with pytest.raises(ValidationFailedError, match="duplicate"):
        duplicate = source.replace(
            '"schema_version": 1,',
            '"schema_version": 1, "schema_version": 1,',
        )
        load_manifest(duplicate)
    with pytest.raises(ValidationFailedError, match="unknown voucher kinds"):
        unknown = source.replace(
            '"kinds": {',
            '"kinds": {"NOT_A_KIND": {"result": "PENDING", '
            '"artifact": "", "reviewer": "", "reason": ""},',
        )
        load_manifest(unknown)


def test_cli_blocks_incomplete_evidence_and_preserves_existing_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    matrix = tmp_path / "evidence.json"
    monkeypatch.setattr("sys.argv", ["verify_release", "--template-output", str(matrix)])
    assert main() == 0
    original = matrix.read_text(encoding="utf-8")
    assert main() == 2
    assert matrix.read_text(encoding="utf-8") == original
    monkeypatch.setattr("sys.argv", ["verify_release", "--manifest", str(matrix)])
    assert main() == 1
    assert "B45 BLOCKED" in capsys.readouterr().out
