"""Export Catalog product fields and option-source contracts for Identity."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from catalog.domain.field_registry import registry
from catalog.domain.option_sources import OPTION_SOURCES
from catalog.tasks.field_context import MANAGE_PERMISSIONS, READ_PERMISSIONS

TARGET = Path(__file__).resolve().parents[2] / "identity/src/identity/data/catalog_fields.json"


def document() -> str:
    return (
        json.dumps(
            {
                entity: {
                    "fields": list(registry.get(entity).fields),
                    "forms": {
                        key: asdict(field) for key, field in registry.get(entity).fields.items()
                    },
                    "permissions": {
                        "read": READ_PERMISSIONS[entity],
                        "write": MANAGE_PERMISSIONS[entity],
                    },
                    "option_sources": {
                        key: asdict(source) for key, source in OPTION_SOURCES.items()
                    },
                }
                for entity in (
                    "catalog.product_family",
                    "catalog.item",
                    "catalog.company_product_authoring_configuration",
                )
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if TARGET.read_text(encoding="utf-8") != document():
            raise SystemExit("Catalog field contract is stale")
    else:
        TARGET.write_text(document(), encoding="utf-8")


if __name__ == "__main__":
    main()
