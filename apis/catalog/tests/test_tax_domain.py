from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError

from catalog.domain.tax import classification_matches, signature, validate_components
from catalog.schemas.tax import (
    BindingInput,
    ClassificationInput,
    ClassificationMatch,
    ComponentInput,
    Evidence,
)
from tests.tax_factories import EVIDENCE, components


def test_sourced_cess_percentage_can_exceed_one_hundred() -> None:
    row = ComponentInput(
        component_key="CESS",
        component="CESS",
        kind="PERCENT",
        percentage=Decimal("125.5000"),
        position=1,
        rounding_mode="HALF_UP",
    )
    assert row.percentage == Decimal("125.5")
    validate_components(
        "INTER_STATE", "TAXABLE", [ComponentInput.model_validate(components("INTER_STATE")[0]), row]
    )
    assert signature([*map(ComponentInput.model_validate, components("INTER_STATE")), row])[2]


def test_exact_cess_basis_and_classification_matching() -> None:
    gst = [ComponentInput.model_validate(entry) for entry in components("INTER_STATE")]
    cess = ComponentInput(
        component_key="CESS",
        component="CESS",
        kind="FIXED_PER_UNIT",
        amount=Decimal("2"),
        currency="INR",
        unit_id=uuid7(),
        basis_quantity=Decimal("4"),
        rounding_mode="HALF_UP",
        position=1,
    )
    equivalent = cess.model_copy(update={"amount": Decimal("1"), "basis_quantity": Decimal("2")})
    assert signature([*gst, cess]) == signature([*gst, equivalent])
    assert signature(gst) == (Fraction(5), "HALF_UP", ())
    split = [ComponentInput.model_validate(entry) for entry in components("INTRA_STATE")]
    assert signature(split) == signature(gst)
    down = [entry.model_copy(update={"rounding_mode": "DOWN"}) for entry in gst]
    assert signature(down) != signature(gst)
    for system, code in (("HSN", "1234"), ("SAC", "991234")):
        exact = ClassificationMatch.model_validate({"code_system": system, "code": code})
        assert classification_matches(system, code, exact)
        assert not classification_matches(system, code + "12", exact)
        prefix = exact.model_copy(update={"match_kind": "PREFIX"})
        assert classification_matches(system, code + "12", prefix)
        assert not classification_matches("OTHER", code, prefix)
    entries = [ComponentInput.model_validate(entry) for entry in components("INTRA_STATE")]
    for first, second in (
        (Decimal(0), Decimal(5)),
        (Decimal(21), Decimal(21)),
        (Decimal("NaN"), Decimal(5)),
    ):
        with pytest.raises(ValidationFailedError):
            validate_components(
                "INTRA_STATE",
                "TAXABLE",
                [
                    entries[0].model_copy(update={"percentage": first}),
                    entries[1].model_copy(update={"percentage": second}),
                ],
            )


def test_native_contexts_nil_and_component_shape() -> None:
    for context in ("INTRA_STATE", "INTRA_UT", "INTER_STATE"):
        for treatment, rate in (("TAXABLE", "5"), ("NIL_RATED", "0")):
            validate_components(
                context,
                treatment,
                [ComponentInput.model_validate(x) for x in components(context, rate)],
            )
    valid = [ComponentInput.model_validate(x) for x in components("INTRA_STATE")]
    cases = [
        ("OTHER", "TAXABLE", valid),
        ("INTRA_STATE", "EXEMPT", valid),
        ("INTRA_STATE", "TAXABLE", []),
        ("INTRA_STATE", "TAXABLE", valid * 9),
        ("INTRA_STATE", "TAXABLE", valid * 2),
        ("INTER_STATE", "TAXABLE", valid),
        ("INTRA_STATE", "NIL_RATED", valid),
        (
            "INTRA_STATE",
            "TAXABLE",
            [x.model_copy(update={"percentage": Decimal(0)}) for x in valid],
        ),
        ("INTRA_STATE", "TAXABLE", [x.model_copy(update={"percentage": None}) for x in valid]),
    ]
    for context, treatment, entries in cases:
        with pytest.raises(ValidationFailedError):
            validate_components(context, treatment, entries)
    zero = [ComponentInput.model_validate(x) for x in components("INTER_STATE", "0")]
    cess = ComponentInput(
        component_key="CESS",
        component="CESS",
        kind="PERCENT",
        percentage=Decimal("1"),
        position=1,
        rounding_mode="HALF_UP",
    )
    with pytest.raises(ValidationFailedError):
        validate_components("INTER_STATE", "NIL_RATED", [*zero, cess])
    base: dict[str, Any] = {
        "component_key": "CGST",
        "component": "CGST",
        "kind": "PERCENT",
        "percentage": Decimal("1"),
        "position": 0,
        "rounding_mode": "HALF_UP",
    }
    for update in (
        {"amount": "1"},
        {"percentage": None},
        {"percentage": "101"},
        {"kind": "FIXED_PER_UNIT"},
        {"percentage": 0.1},
    ):
        with pytest.raises(ValidationError):
            ComponentInput.model_validate({**base, **update})


def test_classification_and_official_evidence_validation() -> None:
    base = {
        **EVIDENCE,
        "valid_from": "2090-01-01",
        "description": "Synthetic",
        "expected_generation": 1,
        "expected_source_version": 2,
    }
    for system, kind, code in (("HSN", "GOODS", "1234"), ("SAC", "SERVICE", "991234")):
        ClassificationInput.model_validate(
            {**base, "code_system": system, "item_kind": kind, "code": code}
        )
    for system, kind, code in (
        ("HSN", "SERVICE", "1234"),
        ("SAC", "SERVICE", "123456"),
        ("HSN", "GOODS", "12345"),
    ):
        with pytest.raises(ValidationError):
            ClassificationInput.model_validate(
                {**base, "code_system": system, "item_kind": kind, "code": code}
            )
    for url in (
        "http://cbic.gov.in/x",
        "https://example.com/x",
        "https://user@cbic.gov.in/x",
        "https://cbic.gov.in:444/x",
        "https:///x",
        "https://cbic.gov.in:bad/x",
    ):
        with pytest.raises(ValidationError):
            Evidence(**{**EVIDENCE, "source_url": url})
    binding = {
        "scope_id": "00000000-0000-0000-0000-000000000001",
        "direction": "SALE",
        "bundle": "TREATMENT",
        "mode": "INHERIT",
        "valid_from": "2090-01-01",
        "expected_generation": 1,
        "expected_source_version": 2,
    }
    BindingInput.model_validate(binding)
    BindingInput.model_validate(
        {
            **binding,
            "mode": "OVERRIDE",
            "treatment": "EXEMPT",
            "tax_category_id": binding["scope_id"],
            "exemption_reason": "Synthetic",
        }
    )
    with pytest.raises(ValidationError):
        BindingInput.model_validate({**binding, "treatment": "EXEMPT"})


def test_split_gst_rounding_and_chapter_99_are_domain_rules() -> None:
    split = [ComponentInput.model_validate(entry) for entry in components("INTRA_STATE")]
    validate_components("INTRA_STATE", "TAXABLE", split)
    mixed = [split[0], split[1].model_copy(update={"rounding_mode": "UP"})]
    with pytest.raises(ValidationFailedError, match="rounding"):
        validate_components("INTRA_STATE", "TAXABLE", mixed)
    for code in ("9954", "995411", "99541100"):
        with pytest.raises(ValidationError):
            ClassificationMatch.model_validate({"code_system": "HSN", "code": code})
    assert ClassificationMatch.model_validate({"code_system": "HSN", "code": "0999"})
    with pytest.raises(ValidationError):
        ClassificationMatch.model_validate({"code_system": "SAC", "code": "981234"})
