"""Validated registration replaces growing dispatch switches in the new framework."""

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, TypeVar

from reports.domain.reporting.contracts import DatasetDefinition, MetricDefinition, ReportDefinition

Handler = TypeVar("Handler")


@dataclass(frozen=True)
class Registration(Generic[Handler]):
    definition: ReportDefinition
    handler: Handler


class Registry(Generic[Handler]):
    def __init__(
        self,
        registrations: Iterable[Registration[Handler]],
        datasets: Iterable[DatasetDefinition],
        metrics: Iterable[MetricDefinition],
    ) -> None:
        data = tuple(datasets)
        measures = tuple(metrics)
        entries = tuple(registrations)
        self.datasets = MappingProxyType({row.key: row for row in data})
        self.metrics = MappingProxyType({row.key: row for row in measures})
        self.reports = MappingProxyType(
            {(row.definition.code, row.definition.version): row for row in entries}
        )
        if len(data) != len(self.datasets) or len(measures) != len(self.metrics):
            raise ValueError("duplicate dataset or metric")
        if len(entries) != len(self.reports):
            raise ValueError("duplicate report code/version")
        self._validate_datasets()
        self._validate_metrics()
        for entry in entries:
            self._validate_report(entry)
            for mapping in entry.definition.drilldowns:
                if mapping.key == "row_detail":
                    continue
                if mapping.version != 1 or not any(
                    code == mapping.target for code, _ in self.reports
                ):
                    raise ValueError("drilldown references an unavailable target or version")

    def resolve(self, code: str, version: int | None = None) -> Registration[Handler]:
        if version is None:
            versions = [key[1] for key in self.reports if key[0] == code]
            if not versions:
                raise KeyError(code)
            version = max(versions)
        return self.reports[(code, version)]

    def _validate_datasets(self) -> None:
        for dataset in self.datasets.values():
            fields = set(dataset.dimensions) | set(dataset.measures)
            if dataset.version < 1 or not dataset.identity or not set(dataset.identity) <= fields:
                raise ValueError("dataset requires version and a declared unique grain")
            if set(dataset.dimensions) & set(dataset.measures):
                raise ValueError("dataset dimension and measure overlap")
            for join in dataset.joins:
                target = self.datasets.get(join.target)
                if (
                    target is None
                    or join.local_key not in fields
                    or join.remote_key not in target.dimensions
                    or (join.cardinality == "ONE_TO_MANY" and not join.preaggregate)
                ):
                    raise ValueError("invalid or fan-out dataset join")

    def _validate_metrics(self) -> None:
        visited: set[str] = set()

        def visit(key: str, ancestors: frozenset[str]) -> None:
            if key in ancestors or key not in self.metrics:
                raise ValueError("metric cycle or missing dependency")
            if key in visited:
                return
            metric = self.metrics[key]
            if metric.version < 1 or (metric.behavior == "RATIO" and len(metric.dependencies) != 2):
                raise ValueError("invalid metric version or ratio operands")
            for dependency in metric.dependencies:
                visit(dependency, ancestors | {key})
            visited.add(key)

        for key in self.metrics:
            visit(key, frozenset())

    def _validate_report(self, entry: Registration[Handler]) -> None:
        row = entry.definition
        if entry.handler is None or row.version < 1 or not row.permissions or not row.views:
            raise ValueError("report requires handler, version, permission and views")
        if not row.datasets or not set(row.datasets) <= self.datasets.keys():
            raise ValueError("report references an unknown dataset")
        if not set(row.metrics) <= self.metrics.keys():
            raise ValueError("report references an unknown metric")
        if len({view.key for view in row.views}) != len(row.views):
            raise ValueError("duplicate view key")
        for view in row.views:
            if (
                view.calculation in {"balance_standard", "balance_comparison"}
                and row.code != "BALANCE_SHEET"
            ):
                raise ValueError("balance view requires Balance Sheet data")
            if view.calculation == "party_balances" and row.code not in {
                "OUTSTANDING_BILLS",
                "ADVANCES",
            }:
                raise ValueError("party balance view requires bill data")
            if (
                view.calculation in {"profit_statement", "profit_comparison"}
                and row.code != "PROFIT_LOSS"
            ):
                raise ValueError("profit view requires Profit and Loss data")
            if (
                view.calculation in {"credit_positions", "credit_events"}
                and row.code != "INVOICE_CREDIT_REGISTER"
            ):
                raise ValueError("credit views require native invoice credit data")
            if view.order != ("ordinal",) or view.calculation not in {
                "detail",
                "party_balances",
                "credit_positions",
                "credit_events",
                "profit_statement",
                "profit_comparison",
                "balance_standard",
                "balance_comparison",
            }:
                raise ValueError("view ordering or calculation is unavailable")
            fields = {column.key for column in view.columns}
            if not fields or len(fields) != len(view.columns) or not view.order:
                raise ValueError("view requires unique typed columns and stable ordering")
            for column in view.columns:
                if column.metric is not None and column.metric not in row.metrics:
                    raise ValueError("column references an undeclared metric")
                if column.kind == "MONEY" and column.currency_key not in fields:
                    raise ValueError("money column requires a declared currency column")
