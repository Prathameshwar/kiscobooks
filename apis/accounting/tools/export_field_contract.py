"""Generate Identity's Accounting field allowlist without cross-service ORM imports."""

import argparse
import json
from pathlib import Path

from accounting.financial_resources import FINANCIAL_RESOURCES
from accounting.resources import RESOURCES
from accounting.stock_resources import STOCK_RESOURCES
from accounting.schemas.metadata import resolved_schema
from accounting.tasks.access import permission

TARGET = Path(__file__).resolve().parents[2] / "identity/src/identity/data/accounting_fields.json"


def document() -> str:
    entities = {}
    for spec in (*RESOURCES, *FINANCIAL_RESOURCES, *STOCK_RESOURCES):
        fields = (
            resolved_schema(spec.detail)["properties"] | resolved_schema(spec.create)["properties"]
        )
        forms = {}
        for key, field in spec.create.model_fields.items():
            column = spec.model.__table__.columns.get(key)
            forms[key] = {
                "required": field.is_required(),
                "hideable": column is not None and column.nullable and key not in spec.immutable,
            }
        entities["accounting." + spec.name] = {
            "permissions": {"read": permission(spec, "read"), "write": permission(spec, "manage")},
            "fields": fields,
            "forms": forms,
        }
    return json.dumps(entities, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = document()
    if args.check:
        if TARGET.read_text(encoding="utf-8") != generated:
            raise SystemExit("Accounting field contract is stale")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(generated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
