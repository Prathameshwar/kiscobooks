"""Export the Accounting event/evidence matrix without importing Audit models."""

import json
from pathlib import Path

from accounting.events.audit_contract import AUDIT_EVENTS, BANK_AUDIT_ACTIONS
from accounting.events.evidence import BANK_SAFE_FIELDS, SAFE_FIELDS
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.resources import BY_NAME
from accounting.stock_resources import STOCK_RESOURCES, STOCK_SAFE_FIELDS
from accounting.tasks.financial_opening import OPENING_AUDIT_FIELDS


def document() -> str:
    resources = BY_NAME | FINANCIAL_BY_NAME | {spec.name: spec for spec in STOCK_RESOURCES}
    rows = {}
    for name in sorted(AUDIT_EVENTS):
        entity, action = name.rsplit(".", 1)
        spec = resources.get(entity.removeprefix("accounting."))
        private = {
            **{
                f"accounting.{name}.{action}": "access" if action == "export" else "money"
                for name in (
                    "financial_opening_revision",
                    "financial_opening_entry",
                    "financial_opening_chunk",
                    "financial_opening_import",
                )
                for action in ("create", "update", "export")
            },
            "accounting.stock_opening_control.export": "access",
            **{
                f"accounting.stock_opening_control.{action}": "money"
                for action in ("create", "finalize", "reopen", "replace", "adopt", "confirm_zero")
            },
            **{
                f"accounting.import_job.{action}": "access"
                if action == "export"
                else "system"
                if action == "cleanup"
                else "admin"
                for action in ("create", "update", "export", "cleanup")
            },
            "accounting.voucher_execution.record": "system",
            "accounting.stock_retirement.check": "system",
            "accounting.stock_policy.inspect": "system",
            "accounting.stock_projection.rebuild": "system",
            "accounting.reporting.captured": "system",
            "accounting.reporting.snapshotted": "system",
            "accounting.reporting.snapshot_requested": "system",
            "accounting.reporting.snapshot_started": "system",
            "accounting.reporting.snapshot_failed": "system",
            "accounting.voucher_money_intent.prepare": "money",
            "accounting.voucher_money_intent.commit": "money",
            "accounting.voucher_money_intent.cancel": "system",
            "accounting.voucher_money_allocation.create": "money",
            "accounting.invoice_record.prepare": "money",
            "accounting.exchange_rate_quote.create": "money",
            "accounting.exchange_rate_quote.approve": "money",
            "accounting.exchange_rate_quote.withdraw": "money",
            "accounting.exchange_rate_usage.create": "money",
            "accounting.party_opening_balance.create": "money",
            "accounting.party_opening_balance.withdraw": "money",
        }
        if spec is None:
            rows[name] = {
                "entity_type": entity,
                "action": name,
                "category": private[name],
                "safe_fields": sorted(
                    OPENING_AUDIT_FIELDS[entity.removeprefix("accounting.")] | {"base_currency"}
                )
                if entity.removeprefix("accounting.") in OPENING_AUDIT_FIELDS
                else ["source_kind", "status"]
                if entity == "accounting.exchange_rate_quote"
                else [
                    "account_id",
                    "amount",
                    "base_amount",
                    "base_currency",
                    "currency",
                    "party_id",
                    "role",
                    "side",
                    "status",
                ]
                if entity == "accounting.party_opening_balance"
                else [],
            }
            continue
        rows[name] = {
            "entity_type": entity,
            "action": name,
            "category": "access"
            if action in {"read", "export"}
            else "money"
            if spec.lifecycle == "command" or spec.name in BANK_AUDIT_ACTIONS
            else "admin",
            "safe_fields": sorted(
                (
                    STOCK_SAFE_FIELDS
                    if spec in STOCK_RESOURCES
                    else BANK_SAFE_FIELDS
                    if spec.name in BANK_AUDIT_ACTIONS
                    else SAFE_FIELDS
                )
                & spec.detail.model_fields.keys()
            ),
        }
    return json.dumps(rows, indent=2) + "\n"


if __name__ == "__main__":
    Path("contracts/audit-events.json").write_text(document(), encoding="utf-8", newline="\n")
