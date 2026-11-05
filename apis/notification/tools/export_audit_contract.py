"""Export or check the exact signed audit publisher contract."""

import argparse
import json
from pathlib import Path

from notification.audit import _SAFE_VALUES
from notification.tasks.audit_publisher import AUDIT_EVENT_TYPES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    contract = {
        name: {
            "entity_type": name.rsplit(".", 1)[0],
            "action": name,
            "categories": ["admin", "system"],
            "safe_values": sorted(_SAFE_VALUES),
            "context_fields": ["notification_realm", "notification_space_id"],
        }
        for name in sorted(AUDIT_EVENT_TYPES)
    }
    content = json.dumps(contract, indent=2) + "\n"
    output = Path(__file__).resolve().parents[1] / "contracts/audit-events.json"
    if args.check:
        return int(not output.exists() or output.read_text(encoding="utf-8") != content)
    output.parent.mkdir(exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
