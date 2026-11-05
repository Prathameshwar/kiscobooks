"""Presentation settings carry no financial facts and never change a calculation."""

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator
from reporting_contract.contract import Contract

Period = Literal["CURRENT", "COMPARATIVE"]
NODE_PATTERN = (
    r"^(?:head|group|account):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
NodeKey = Annotated[str, Field(pattern=NODE_PATTERN, max_length=48)]


class TrialPresentation(Contract):
    period: Period = "CURRENT"
    hierarchy: Literal["CURRENT", "ALL"] = "CURRENT"
    level: Literal["HEADS", "GROUPS", "ALL_GROUPS", "LEDGERS"] = "GROUPS"
    expanded: list[NodeKey] = Field(default_factory=list, max_length=2000)
    collapsed: list[NodeKey] = Field(default_factory=list, max_length=2000)
    show_zero: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalized_nodes(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        for key in ("expanded", "collapsed"):
            nodes = result.get(key, [])
            if isinstance(nodes, list) and len(nodes) > 2000:
                raise ValueError("hierarchy overrides must contain at most 2000 nodes")
            if isinstance(nodes, list) and all(isinstance(node, str) for node in nodes):
                result[key] = sorted(set(nodes))
        if isinstance(result.get("expanded"), list) and isinstance(result.get("collapsed"), list):
            if any(node in result["collapsed"] for node in result["expanded"]):
                raise ValueError("a hierarchy node cannot be both expanded and collapsed")
        return result
