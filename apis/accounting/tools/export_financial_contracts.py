"""Export reproducible financial source and Catalog evidence schemas (versioned)."""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from accounting.events.financial_contract import JournalPosted, PeriodChanged
from accounting.schemas.catalog_tax_events import ClassificationChanged, RateChanged, RuleChanged
from accounting.schemas.charge_tax import TaxComputation, TaxComputationV2

ROOT = Path(__file__).resolve().parents[1] / "contracts"
CONTRACTS: dict[str, type[BaseModel]] = {
    "journal-posted-v1": JournalPosted,
    "fiscal-period-changed-v1": PeriodChanged,
    "catalog-tax-computation-v1": TaxComputation,
    "catalog-tax-computation-v2": TaxComputationV2,
    "catalog-tax-classification-changed-v1": ClassificationChanged,
    "catalog-tax-rule-changed-v1": RuleChanged,
    "catalog-tax-rate-changed-v1": RateChanged,
}


def documents() -> dict[str, str]:
    return {
        name: json.dumps(model.model_json_schema(mode="serialization"), indent=2, sort_keys=True)
        + "\n"
        for name, model in CONTRACTS.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, document in documents().items():
        path = ROOT / (name + ".schema.json")
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != document:
                raise SystemExit("Financial schema is stale: " + name)
        else:
            ROOT.mkdir(exist_ok=True)
            path.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
