"""Quiet nested ancestry and a posted clearing account with gross movement."""

import uuid

from financial_fixture import financial_dataset
from fixtures import source


def filtering_dataset():
    facts, ids = financial_dataset()
    cash = next(row.data for row in facts if str(row.source_id) == ids["cash"])
    group = next(row.data for row in facts if str(row.source_id) == cash["group_id"])
    ids |= {name: str(uuid.uuid4()) for name in ("quiet_group", "quiet", "clearing")}
    facts.append(
        source(
            "account_group",
            ids["quiet_group"],
            group | {"code": "QUIET", "name": "Quiet group", "parent_id": cash["group_id"]},
        )
    )
    for name in ("quiet", "clearing"):
        facts.append(
            source(
                "account",
                ids[name],
                cash
                | {
                    "code": name.upper(),
                    "name": name,
                    "kind": "GENERAL",
                    "group_id": ids["quiet_group"] if name == "quiet" else cash["group_id"],
                },
            )
        )
    template = next(
        row for row in facts if row.entity == "journal" and row.data["number"] == "expense"
    )
    journal = str(uuid.uuid4())
    facts.append(
        source(
            "journal",
            journal,
            template.data
            | {
                "number": "clearing",
                "source_id": journal,
                "total_debit": "7.0000",
                "total_credit": "7.0000",
            },
        )
    )
    line = next(
        row.data
        for row in facts
        if row.entity == "journal_line" and row.data["journal_id"] == str(template.source_id)
    )
    for index, side in enumerate(("DEBIT", "CREDIT"), 1):
        facts.append(
            source(
                "journal_line",
                uuid.uuid4(),
                line
                | {
                    "journal_id": journal,
                    "account_id": ids["clearing"],
                    "sequence": index,
                    "side": side,
                    "amount": "7.0000",
                    "base_amount": "7.0000",
                    "party_id": None,
                    "role": None,
                },
            )
        )
    return sorted(facts, key=lambda row: (row.entity, str(row.source_id))), ids
