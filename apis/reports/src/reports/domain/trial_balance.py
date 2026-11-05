"""Versioned Trial Balance topology and exact account-side controls over frozen facts."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.money import RoundingMode, round_for_display

from reports.domain.reporting.contracts import fingerprint
from reports.domain.reporting.opening_coverage import includes_ytd
from reports.domain.statements import Facts, balances, calculation_evidence
from reports.schemas.requests import RunRequest

VERSION = 6
AMOUNTS = (
    "opening_debit",
    "opening_credit",
    "period_debit",
    "period_credit",
    "closing_debit",
    "closing_credit",
)
NATURES = ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE")


def display_residuals(
    rows: list[dict[str, Any]], evidence: dict[str, Any], precision: int, mode: RoundingMode
) -> None:
    """Disclose rounded leaf sums without changing any exact financial amount."""
    sums: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(
        lambda: {key: Decimal(0) for key in AMOUNTS}
    )
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for row in reversed(rows):
            if row["row_kind"] == "TRIAL_BALANCE_CONTROL":
                continue
            rounded = {key: round_for_display(row[key], precision, mode) for key in AMOUNTS}
            leaves = (
                rounded if row["row_kind"] == "ACCOUNT" else sums[row["period"], row["node_key"]]
            )
            row["display_residual"] = {
                key: format(rounded[key] - leaves[key], ".4f")
                for key in AMOUNTS
                if rounded[key] != leaves[key]
            }
            parent = sums[row["period"], row["parent_key"]]
            for key in AMOUNTS:
                parent[key] += leaves[key]
        for row in rows:
            if row["row_kind"] != "TRIAL_BALANCE_CONTROL":
                continue
            leaves = sums[row["period"], "root"]
            row["display_residual"] = {
                key: format(round_for_display(row[key], precision, mode) - leaves[key], ".4f")
                for key in AMOUNTS
                if round_for_display(row[key], precision, mode) != leaves[key]
            }
            evidence["trial_balance"]["periods"][row["period"]]["display_residual"] = row[
                "display_residual"
            ]


def period_rows(
    data: Facts, query: RunRequest, period: str, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Construct a preorder tree without recursion or netting parent-side balances."""
    heads = data.rows["account_head"]
    if len(heads) + len(data.groups) + len(data.accounts) + 1 > maximum:
        raise ConflictError("trial balance hierarchy exceeds result capacity")
    nodes: dict[str, dict[str, Any]] = {}
    children: dict[str, list[str]] = defaultdict(list)

    def add(kind: str, identity: str, source: dict[str, Any], parent: str) -> None:
        key = kind.lower() + ":" + identity
        nodes[key] = {
            "row_kind": kind,
            "node_key": key,
            "parent_key": parent,
            "code": source["code"],
            "name": source["name"],
            "currency": data.currency,
            "period": period,
            "account_count": 0,
            "display_residual": {},
            **{amount: Decimal(0) for amount in AMOUNTS},
        }
        children[parent].append(key)

    for identity, head in heads.items():
        if head["nature"] not in NATURES:
            raise ConflictError("trial balance head classification is unavailable")
        add("HEAD", identity, head, "root")
        nodes["head:" + identity].update(head_id=identity, nature=head["nature"])
    for identity, group in data.groups.items():
        head_id, parent_id = group["head_id"], group["parent_id"]
        if head_id not in heads or (parent_id and parent_id not in data.groups):
            raise ConflictError("trial balance classification has missing ancestry")
        if parent_id and data.groups[parent_id]["head_id"] != head_id:
            raise ConflictError("trial balance classification crosses account heads")
        add("GROUP", identity, group, "group:" + parent_id if parent_id else "head:" + head_id)
        nodes["group:" + identity].update(group_id=identity, head_id=head_id)
    try:
        account_rows = balances(data, query)
    except KeyError as exc:
        raise ConflictError("trial balance account classification is unavailable") from exc
    for account in account_rows:
        identity, group = account["account_id"], account["group_id"]
        add(
            "ACCOUNT",
            identity,
            {"code": account["account_code"], "name": account["account_name"]},
            "group:" + group,
        )
        node = nodes["account:" + identity]
        opening = Decimal(account["opening"])
        node.update(account)
        node.update(
            period=period,
            account_count=1,
            opening_debit=max(opening, Decimal(0)),
            opening_credit=max(-opening, Decimal(0)),
            period_debit=Decimal(account["debit"]),
            period_credit=Decimal(account["credit"]),
            closing_debit=Decimal(account["balance_debit"]),
            closing_credit=Decimal(account["balance_credit"]),
            head_id=data.groups[group]["head_id"],
        )
    for parent, keys in children.items():
        keys.sort(
            key=lambda key: (
                NATURES.index(nodes[key]["nature"]) if parent == "root" else 0,
                nodes[key]["code"],
                key,
            )
        )
    ordered: list[str] = []
    visited: set[str] = set()
    stack = [(key, 0) for key in reversed(children["root"])]
    while stack:
        key, depth = stack.pop()
        if key in visited:
            raise ConflictError("trial balance hierarchy contains repeated nodes")
        node = nodes[key]
        node["depth"], node["child_count"] = depth, len(children[key])
        node["group_child_count"] = sum(
            nodes[child]["row_kind"] == "GROUP" for child in children[key]
        )
        ordered.append(key)
        visited.add(key)
        stack.extend((child, depth + 1) for child in reversed(children[key]))
    if len(ordered) != len(nodes):
        raise ConflictError("trial balance hierarchy contains a cycle or disconnected node")
    totals = {amount: Decimal(0) for amount in AMOUNTS}
    for key in reversed(ordered):
        node = nodes[key]
        ancestor = nodes.get(node["parent_key"])
        target = ancestor if ancestor is not None else totals
        for amount in AMOUNTS:
            target[amount] += node[amount]
        if ancestor is not None:
            ancestor["account_count"] += node["account_count"]
    summary: dict[str, Any] = {
        "account_count": len(account_rows),
        "currency": data.currency,
        "display_residual": {},
        **{amount: format(value, ".4f") for amount, value in totals.items()},
    }
    for kind in ("opening", "period", "closing"):
        difference = totals[kind + "_debit"] - totals[kind + "_credit"]
        summary[kind + "_difference"] = format(difference, ".4f")
        if difference:
            raise ConflictError(f"trial balance {kind} does not reconcile")
    rows = []
    for key in ordered:
        node = nodes[key]
        node["is_zero"] = not any(node[amount] for amount in AMOUNTS)
        for amount in AMOUNTS:
            node[amount] = format(node[amount], ".4f")
        rows.append(node)
    rows.append(
        {
            "row_kind": "TRIAL_BALANCE_CONTROL",
            "node_key": "total",
            "parent_key": "root",
            "code": "",
            "name": "Grand total",
            "period": period,
            "depth": 0,
            "child_count": 0,
            "is_zero": not any(totals.values()),
            "difference": "0.0000",
            "display_residual": {},
            **summary,
        }
    )
    return rows, summary


def calculate(
    data: Facts, query: RunRequest, coverage: dt.date, *, maximum: int = 100000
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    assert query.date_from and query.date_to
    if query.date_from < coverage and not includes_ytd(data.rows, query):
        raise ConflictError("requested history precedes retained owner coverage")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        rows, summary = period_rows(data, query, "CURRENT", maximum)
        periods = {"CURRENT": summary}
        if query.comparative_from and query.comparative_to:
            comparison = query.model_copy(
                update={
                    "date_from": query.comparative_from,
                    "date_to": query.comparative_to,
                    "comparative_from": None,
                    "comparative_to": None,
                }
            )
            assert comparison.date_from is not None
            if comparison.date_from < coverage and not includes_ytd(data.rows, comparison):
                raise ConflictError(
                    "requested comparative history precedes retained owner coverage"
                )
            extra, periods["COMPARATIVE"] = period_rows(
                data, comparison, "COMPARATIVE", maximum - len(rows)
            )
            rows.extend(extra)
    return rows, evidence(data, query, coverage, rows, periods)


def evidence(
    data: Facts,
    query: RunRequest,
    coverage: dt.date,
    rows: list[dict[str, Any]],
    periods: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    topology = [
        {key: row[key] for key in ("node_key", "parent_key", "period", "depth", "code", "name")}
        for row in rows
    ]
    return calculation_evidence(data, query, coverage, rows) | {
        "rule_hash": fingerprint({"trial_balance": VERSION, "arithmetic": "LEAF_SIDES"}),
        "trial_balance": {
            "version": VERSION,
            "hierarchy_hash": fingerprint(topology),
            "periods": periods,
        },
    }
