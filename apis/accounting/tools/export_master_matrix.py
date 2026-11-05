"""Generate the reviewable native master field and resource matrix."""

import argparse
import json
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Table

from accounting.resources import RESOURCES
from accounting.schemas import lists as list_schemas
from accounting.schemas.query import MasterQuery
from accounting.tasks.access import permission
from accounting.tasks.commands import READ_ONLY

TARGET = Path(__file__).resolve().parents[3] / "docs/accounting-master-matrix.json"


def document() -> str:
    result: dict[str, Any] = {}
    for spec in RESOURCES:
        query = MasterQuery.model_json_schema()["properties"]
        searchable = [key for key in ("code", "name", "label") if key in spec.detail.model_fields]
        supported = {"limit", "cursor", "sort"} | set(spec.detail.model_fields)
        if searchable:
            supported.add("q")
        if spec.lifecycle == "dates":
            supported.add("as_of")
        result[spec.name] = {
            "path": spec.path,
            "lifecycle": spec.lifecycle,
            "read_only": spec.name in READ_ONLY,
            "permission_read": permission(spec, "read"),
            "permission_manage": permission(spec, "manage"),
            "immutable_fields": sorted(spec.immutable),
            "references": spec.references,
            "create": spec.create.model_json_schema(),
            "update": spec.update.model_json_schema(),
            "detail": spec.detail.model_json_schema(),
            "list": getattr(list_schemas, spec.model.__name__ + "ListItem").model_json_schema(),
            "query": {key: definition for key, definition in query.items() if key in supported},
            "search_fields": searchable,
            "sort_fields": [
                key for key in ("id", "name", "sort_order") if key in spec.detail.model_fields
            ],
            "importable": spec.name not in READ_ONLY,
            "export_path": "/exports/" + spec.path,
            "server_fields": sorted(set(spec.detail.model_fields) - set(spec.create.model_fields)),
            "indexes": {
                index.name: [column.name for column in index.columns]
                for index in cast(Table, spec.model.__table__).indexes
            },
        }
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = document()
    if args.check:
        if TARGET.read_text(encoding="utf-8") != generated:
            raise SystemExit("Accounting master matrix is stale")
    else:
        TARGET.write_text(generated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
