"""Bounded, exact bulk envelopes and dependency order, without service policy."""

from __future__ import annotations

import hashlib
import re
import uuid
from graphlib import CycleError, TopologicalSorter
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from billing_platform.idempotency import canonical_json

MAX_ROWS = 2000
MAX_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_ROWS = 100
KEY = r"^[a-z0-9][a-z0-9_.-]{0,63}$"


class ExactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BulkTarget(ExactModel):
    id: uuid.UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=100)
    external_system: str | None = Field(default=None, min_length=1, max_length=64)
    external_key: str | None = Field(default=None, min_length=1, max_length=250)
    record: str | None = Field(default=None, pattern=KEY)
    field: str = Field(default="id", pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,3}$")

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.id is not None and self.id.int == 0:
            raise ValueError("target requires a real identity")
        if (self.external_system is None) != (self.external_key is None):
            raise ValueError("external system and key must be supplied together")
        if self.record is not None and any(
            value is not None for value in (self.id, self.code, self.external_key)
        ):
            raise ValueError("staged targets cannot also select an existing identity")
        if self.record is None and self.field != "id":
            raise ValueError("a staged target field needs its logical record")
        return self


class BulkRecord(ExactModel):
    key: str = Field(pattern=KEY)
    change_set: str = Field(pattern=KEY)
    resource: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    action: str = Field(default="AUTO", pattern=r"^[A-Z][A-Z_]{0,39}$")
    target: BulkTarget = Field(default_factory=BulkTarget)
    data: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    clear_fields: list[str] = Field(default_factory=list, max_length=100)
    source_sheet: str = Field(default="JSON", min_length=1, max_length=100)
    source_row: int = Field(default=1, strict=True, ge=1, le=MAX_ROWS + 2)

    @field_validator("data")
    @classmethod
    def exact_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        canonical_json(value, maximum_bytes=65536)
        return value

    @model_validator(mode="after")
    def bounded_names(self) -> Self:
        if len(set(self.depends_on)) != len(self.depends_on) or any(
            not re.fullmatch(KEY, key) for key in self.depends_on
        ):
            raise ValueError("dependencies require unique logical row keys")
        if len(set(self.clear_fields)) != len(self.clear_fields) or any(
            not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) for key in self.clear_fields
        ):
            raise ValueError("clear fields require unique native field names")
        if set(self.clear_fields) & self.data.keys():
            raise ValueError("a field cannot be supplied and cleared together")
        return self


class BulkBatch(ExactModel):
    schema_version: Literal[1] = 1
    mode: Literal["CREATE_ONLY", "UPDATE_ONLY", "UPSERT"] = "CREATE_ONLY"
    atomicity: Literal["CHANGE_SET", "ATOMIC"] = "CHANGE_SET"
    on_error: Literal["STOP", "CONTINUE_INDEPENDENT"] = "STOP"
    records: list[BulkRecord] = Field(min_length=1, max_length=MAX_ROWS)

    @model_validator(mode="after")
    def bounded_graph(self) -> Self:
        canonical_json(self.model_dump(mode="json"), maximum_bytes=MAX_BYTES)
        ordered_records(self.records)
        sets: dict[str, int] = {}
        for row in self.records:
            sets[row.change_set] = sets.get(row.change_set, 0) + 1
        if max(sets.values()) > MAX_AGGREGATE_ROWS:
            raise ValueError("one change set may contain at most 100 commands")
        if self.atomicity == "ATOMIC" and (len(sets) > 100 or len(self.records) > 1000):
            raise ValueError("atomic jobs allow at most 100 aggregates and 1000 commands")
        return self


def references(value: Any) -> set[str]:
    if isinstance(value, dict):
        if "$ref" in value:
            if (
                set(value) != {"$ref", "field"}
                or not isinstance(value["$ref"], str)
                or not re.fullmatch(KEY, value["$ref"])
                or not isinstance(value["field"], str)
                or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,3}", value["field"])
            ):
                raise ValueError("invalid staged reference")
            return {value["$ref"]}
        return set().union(*(references(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(*(references(child) for child in value))
    return set()


def resolve_references(value: Any, results: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        if "$ref" in value:
            references(value)
            selected: Any = results[value["$ref"]]
            for field in value["field"].split("."):
                selected = selected[field]
            if not isinstance(selected, str | int | bool) or selected is None:
                raise ValueError("staged reference must select a scalar result")
            return selected
        return {key: resolve_references(child, results) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_references(child, results) for child in value]
    return value


def ordered_records(records: list[BulkRecord]) -> list[BulkRecord]:
    by_key = {row.key: row for row in records}
    if len(by_key) != len(records):
        raise ValueError("logical record keys must be unique")
    graph = {
        row.key: set(row.depends_on)
        | references(row.data)
        | ({row.target.record} if row.target.record else set())
        for row in records
    }
    if any(not parents <= by_key.keys() for parents in graph.values()):
        raise ValueError("staged dependency is missing")
    sets: dict[str, set[str]] = {row.change_set: set() for row in records}
    for key, parents in graph.items():
        sets[by_key[key].change_set] |= {
            by_key[parent].change_set
            for parent in parents
            if by_key[parent].change_set != by_key[key].change_set
        }
    try:
        order = list(
            TopologicalSorter(
                {key: sorted(parents) for key, parents in graph.items()}
            ).static_order()
        )
        set_order = list(
            TopologicalSorter(
                {key: sorted(parents) for key, parents in sets.items()}
            ).static_order()
        )
    except CycleError as exc:
        raise ValueError("staged dependencies or change sets are cyclic") from exc
    depth: dict[str, int] = {}
    for key in order:
        depth[key] = 1 + max((depth[parent] for parent in graph[key]), default=0)
    if max(depth.values(), default=0) > 32 or sum(map(len, graph.values())) > 20000:
        raise ValueError("dependency graph exceeds depth or edge limit")
    rank = {key: position for position, key in enumerate(set_order)}
    return sorted((by_key[key] for key in order), key=lambda row: rank[row.change_set])


def selection_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value, maximum_bytes=MAX_BYTES)).hexdigest()
