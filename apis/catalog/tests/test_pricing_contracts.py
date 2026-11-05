import uuid
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.money import MoneyError
from fastapi import FastAPI
from pydantic import ValidationError

from catalog.schemas import pricing as s


def test_native_price_contracts_reject_ambiguous_and_inexact_inputs() -> None:
    key = str(uuid.uuid4())
    dated = {"expected_generation": 1, "expected_source_version": 1, "valid_from": "2090-01-01"}
    plan = {
        "code": "SALE",
        "name": "Sale",
        "purpose": "SALE",
        "price_level_id": key,
        "currency": "INR",
        "tax_basis": "EXCLUSIVE",
    }
    draft = {
        "series_id": key,
        "numeric_revision_id": key,
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "100",
        "price_basis_quantity": "1",
    }
    guard = {
        **dated,
        "item_id": key,
        "unit_revision_id": key,
        "numeric_revision_id": key,
        "currency": "INR",
        "rule_kind": "FIXED_MIN",
        "amount": "1",
        "price_basis_quantity": "1",
        "source_reference": "Reviewed",
    }
    cases: list[tuple[type[s.PricingInput], dict[str, Any]]] = [
        (s.PlanCreate, {**plan, "name": "  "}),
        (s.PlanCreate, {**plan, "name": "x\ny"}),
        (s.PlanCreate, {**plan, "price_level_id": None}),
        (s.PlanCreate, {**plan, "purpose": "PURCHASE"}),
        (s.DatedInput, {**dated, "valid_to": "2089-01-01"}),
        (s.DatedInput, {**dated, "supersedes_id": key}),
        (s.PolicyInput, {**dated, "default_level_id": key, "missing_price_policy": "FALLBACK"}),
        (
            s.PolicyInput,
            {
                **dated,
                "default_level_id": key,
                "fallback_level_id": key,
                "missing_price_policy": "FALLBACK",
            },
        ),
        (s.DraftInput, {**draft, "amount": 0.1}),
        (s.DraftInput, {**draft, "amount": "0.00001"}),
        (s.DraftInput, {**draft, "amount": None}),
        (s.DraftInput, {**draft, "tiers": [{"min_quantity": "0", "amount": "1"}]}),
        (
            s.DraftInput,
            {
                **draft,
                "formula": {
                    "recipe": "MRP_LESS_PERCENT",
                    "percentage": "10",
                    "jurisdiction": "IN",
                    "rounding_mode": "UP",
                },
            },
        ),
        (s.DraftInput, {**draft, "valid_to": "2089-01-01"}),
        (
            s.DraftInput,
            {
                **draft,
                "amount": None,
                "price_method": "TIERS",
                "tiers": [{"min_quantity": "0", "amount": "1"}],
                "purchase_term": {
                    "gross_amount": "1",
                    "discount_kind": "NONE",
                    "discount_value": "0",
                },
            },
        ),
        (s.FormulaInput, {"recipe": "MRP_LESS_PERCENT", "percentage": "10", "rounding_mode": "UP"}),
        (
            s.FormulaInput,
            {"recipe": "REFERENCE_COST_PLUS_MARKUP", "percentage": "10", "rounding_mode": "UP"},
        ),
        (
            s.FormulaInput,
            {
                "recipe": "REFERENCE_COST_TARGET_MARGIN",
                "percentage": "100",
                "estimate_kind": "STANDARD_ESTIMATE",
                "rounding_mode": "UP",
            },
        ),
        (s.GuardInput, {**guard, "percentage": "10"}),
        (
            s.GuardInput,
            {
                **guard,
                "amount": None,
                "rule_kind": "MIN_MARGIN",
                "percentage": "100",
                "estimate_kind": "STANDARD_ESTIMATE",
            },
        ),
        (s.CommercialScopeInput, {"owner_kind": "GROUP"}),
        (s.CommercialScopeInput, {"owner_kind": "SKU", "item_id": key, "group_id": key}),
        (s.ScopeInput, {"item_id": key, "lot_id": key}),
        (
            s.ResolveInput,
            {
                "item_id": key,
                "unit_revision_id": key,
                "currency": "INR",
                "as_of": "2090-01-01",
                "quantity": "1",
                "allocated_cost": "5",
            },
        ),
    ]
    for model, body in cases:
        with pytest.raises((ValidationError, ValidationFailedError, MoneyError)):
            model.model_validate(body)
    assert s.PlanCreate.model_validate({**plan, "name": " Sale "}).name == "Sale"
    assert (
        s.FormulaInput(
            recipe="REFERENCE_COST_TARGET_MARGIN",
            percentage=Decimal("25"),
            estimate_kind="STANDARD_ESTIMATE",
            rounding_mode="UP",
        ).percentage
        == 25
    )
    assert s.GuardInput.model_validate(
        {
            **guard,
            "amount": None,
            "rule_kind": "MIN_MARGIN",
            "percentage": "25",
            "estimate_kind": "STANDARD_ESTIMATE",
        }
    )


def test_decimal_wire_schema_matches_required_and_optional_runtime_fields() -> None:
    schema = s.TierInput.model_json_schema()

    def dereference(value: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in value:
            return dict(schema["$defs"][value["$ref"].rsplit("/", 1)[1]])
        return value

    required = schema["properties"]
    assert dereference(required["amount"]).get("type") == "string"
    assert dereference(required["min_quantity"]).get("type") == "string"
    assert {dereference(choice)["type"] for choice in required["max_quantity"]["anyOf"]} == {
        "string",
        "null",
    }
    schema = s.ResolveInput.model_json_schema()
    assert dereference(schema["properties"]["quantity"]).get("type") == "string"


def test_creation_status_codes_are_present_in_openapi(app: FastAPI) -> None:
    from fastapi.routing import APIRoute

    from catalog.api.pricing import router

    spec = app.openapi()
    for route in router.routes:
        if (
            isinstance(route, APIRoute)
            and "POST" in route.methods
            and not route.path.endswith(("/resolve", "/coverage"))
        ):
            assert "201" in spec["paths"][route.path]["post"]["responses"], route.path
