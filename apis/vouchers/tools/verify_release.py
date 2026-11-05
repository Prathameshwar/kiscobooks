"""Check B45's reviewed evidence matrix against the authoritative batch tracker."""

import argparse
import json
from pathlib import Path

from billing_platform.errors import ValidationFailedError

from vouchers.domain.registry import KINDS
from vouchers.domain.release_gate import (
    SCOPE_FIELDS,
    WORKSTREAMS,
    evaluate,
    load_manifest,
    required_cases,
    tracker_file_statuses,
)

ROOT = Path(__file__).resolve().parents[3]
TRACKER = ROOT / "docs" / "voucher-delivery-tracker.md"


def template(*, reservation_selected: bool) -> str:
    pending = {"result": "PENDING", "artifact": "", "reviewer": "", "reason": ""}
    return (
        json.dumps(
            {
                "schema_version": 1,
                "reservation_selected": reservation_selected,
                "scope": {field: "" for field in sorted(SCOPE_FIELDS)},
                "kinds": {kind.code: pending for kind in KINDS},
                "cases": {
                    case: pending
                    for case in sorted(required_cases(reservation_selected=reservation_selected))
                },
                "workstreams": {name: pending for name in sorted(WORKSTREAMS)},
            },
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="reviewed B45 evidence JSON")
    parser.add_argument("--tracker", type=Path, default=TRACKER)
    parser.add_argument("--template-output", type=Path, help="write a pending evidence template")
    parser.add_argument("--reservation-selected", action="store_true")
    args = parser.parse_args()
    if args.template_output:
        if args.manifest:
            parser.error("--template-output and --manifest are exclusive")
        try:
            with args.template_output.open("x", encoding="utf-8") as output:
                output.write(template(reservation_selected=args.reservation_selected))
        except OSError as exc:
            print(f"Cannot create evidence template: {exc}")
            return 2
        print(f"Pending evidence template: {args.template_output}")
        return 0
    if not args.manifest:
        parser.error("--manifest is required for verification")
    if args.reservation_selected:
        parser.error("--reservation-selected only applies to --template-output")
    try:
        manifest = load_manifest(args.manifest.read_text(encoding="utf-8"))
        problems = evaluate(tracker_file_statuses(args.tracker), manifest)
    except (OSError, ValidationFailedError) as exc:
        print(f"B45 evidence invalid: {exc}")
        return 2
    if problems:
        print(f"B45 BLOCKED: {len(problems)} missing or invalid gates")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("B45 evidence-complete; independent review and native results still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
