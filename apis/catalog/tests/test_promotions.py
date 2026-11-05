import copy
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError

from catalog.domain.promotion_deals import same_item_deal_profile
from catalog.schemas.promotions import (
    BuyGetBenefit,
    CouponProgramTerms,
    NativeSelector,
    PromotionTerms,
    StackPolicyTerms,
)


def money(amount: str = "10") -> dict[str, str]:
    return {"amount": amount, "currency": "USD", "basis": "NET_EXCL_TAX"}


def quantity() -> dict[str, Any]:
    return {"quantity": "2", "unit_revision_id": uuid7()}


def terms(benefit: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "currency": "USD",
        "eligible_price_level_ids": [uuid7()],
        "selection_mode": "SNAPSHOT_ON_PUBLISH",
        "condition_groups": [{"minimum_spend": money()}],
        "benefit": benefit or {"kind": "LINE_PERCENT", "percent": "10"},
        "trigger": "AUTOMATIC",
        "starts_at": "2026-09-01T05:30:00+05:30",
        "ends_at": "2026-10-01T00:00:00Z",
        "timezone": "Asia/Kolkata",
        "stack_policy_revision_id": uuid7(),
        "stack_group_id": uuid7(),
        "return_policy_revision_id": uuid7(),
        "priority": 1,
    }


def benefit_cases() -> list[dict[str, Any]]:
    repeat = {"maximum_repeats": 2}
    reward = {
        "reward": quantity(),
        "reward_item_ids": [uuid7()],
        "selection": "LOWEST_REGULAR_UNIT_PRICE",
        **repeat,
    }
    return [
        {"kind": "LINE_PERCENT", "percent": "10"},
        {"kind": "BASKET_PERCENT", "percent": "100", "maximum_benefit": money()},
        {"kind": "LINE_FIXED", "value": money(), "application": "PER_UNIT"},
        {"kind": "LINE_FIXED", "value": money(), "application": "PER_LINE"},
        {"kind": "BASKET_FIXED", "value": money(), "application": "PER_BASKET"},
        {"kind": "QUANTITY", "qualifying": quantity(), "percent": "5", **repeat},
        {
            "kind": "BUY_GET",
            "qualifying": quantity(),
            "pool": "CROSS_ITEM",
            "reward_percent": "100",
            **reward,
        },
        {
            "kind": "BUNDLE_PRICE",
            "components": [{"item_id": uuid7(), "quantity": quantity()}],
            "target": money(),
            **repeat,
        },
        {
            "kind": "MIX_MATCH",
            "pool_item_ids": [uuid7()],
            "choose_quantity": quantity(),
            "target": money(),
            **repeat,
        },
        {"kind": "GIFT", **reward},
    ]


@pytest.mark.parametrize("benefit", benefit_cases())
def test_definition_roundtrip_and_timezone(benefit: dict[str, Any]) -> None:
    parsed = PromotionTerms.model_validate(terms(benefit))
    assert PromotionTerms.model_validate_json(parsed.model_dump_json()) == parsed
    assert parsed.starts_at.isoformat() == "2026-09-01T00:00:00+00:00"
    assert parsed.benefit.kind == benefit["kind"]


@pytest.mark.parametrize(
    "change",
    [
        {"starts_at": "2026-09-01T00:00:00"},
        {"ends_at": "2026-08-01T00:00:00Z"},
        {"timezone": "../bad"},
        {"timezone": "Nowhere/Invalid"},
        {"priority": True},
        {"eligible_price_level_ids": []},
        {"stack_policy_revision_id": 4},
        {"stack_group_id": "00000000-0000-0000-0000-000000000000"},
        {"currency": "EUR"},
        {"custom_fields": {"cf_discount": "90"}},
        {
            "condition_groups": [
                {"selectors": [{"dimension": "CUSTOM_FIELD", "mode": "INCLUDE", "ids": [uuid7()]}]}
            ]
        },
    ],
)
def test_unsafe_or_ambiguous_definitions_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PromotionTerms.model_validate({**terms(), **change})


@pytest.mark.parametrize("percent", [0, "101", 1.2, True, "NaN", "0.00001"])
def test_percent_requires_positive_exact_decimal(percent: Any) -> None:
    with pytest.raises(ValidationError):
        PromotionTerms.model_validate(terms({"kind": "LINE_PERCENT", "percent": percent}))


def test_currency_thresholds_scope_and_duplicates() -> None:
    for benefit in benefit_cases():
        invalid = copy.deepcopy(benefit)
        for key in ("value", "target", "maximum_benefit"):
            if key in invalid:
                invalid[key]["currency"] = "EUR"
                with pytest.raises(ValidationError):
                    PromotionTerms.model_validate(terms(invalid))
        for key in ("reward_item_ids", "pool_item_ids", "components"):
            if key in benefit:
                duplicate = copy.deepcopy(benefit)
                duplicate[key] *= 2
                with pytest.raises(ValidationError):
                    PromotionTerms.model_validate(terms(duplicate))
        if benefit["kind"] in {"GIFT", "BASKET_PERCENT", "BASKET_FIXED"}:
            with pytest.raises(ValidationError):
                PromotionTerms.model_validate({**terms(benefit), "condition_groups": [{}]})
    for kind, application in [("LINE_FIXED", "PER_BASKET"), ("BASKET_FIXED", "PER_LINE")]:
        with pytest.raises(ValidationError):
            PromotionTerms.model_validate(
                terms({"kind": kind, "application": application, "value": money()})
            )
    identity = uuid7()
    with pytest.raises(ValidationError):
        NativeSelector(dimension="SKU", mode="INCLUDE", ids=(identity, identity))
    selector = {"dimension": "CATEGORY", "mode": "INCLUDE", "ids": [identity]}
    attribute = {"attribute_id": uuid7(), "option_ids": [identity], "mode": "INCLUDE"}
    for group in [
        {"selectors": [selector, selector]},
        {"attributes": [attribute, attribute]},
        {"attributes": [{**attribute, "option_ids": [identity, identity]}]},
        {"item_kinds": ["GOODS", "GOODS"]},
    ]:
        with pytest.raises(ValidationError):
            PromotionTerms.model_validate({**terms(), "condition_groups": [group]})
    parsed = PromotionTerms.model_validate(
        {
            **terms(),
            "condition_groups": [
                {
                    "selectors": [selector, {**selector, "mode": "EXCLUDE"}],
                    "attributes": [attribute],
                }
            ],
        }
    )
    assert len(parsed.condition_groups[0].selectors) == 2


def program() -> dict[str, Any]:
    return {
        "promotion_id": uuid7(),
        "code_mode": "SHARED_PUBLIC",
        "code_case": "INSENSITIVE",
        "customer_binding": "NONE",
        "requires_customer": True,
        "starts_at": "2026-09-01T00:00:00Z",
        "ends_at": "2026-10-01T00:00:00Z",
        "limits": [{"limit_id": uuid7(), "kind": "PER_CUSTOMER_USES", "maximum": 1}],
    }


def test_program_identity_limits_and_no_runtime_state() -> None:
    base = program()
    assert CouponProgramTerms.model_validate(base).requires_customer
    assert (
        CouponProgramTerms.model_validate(
            {**base, "limits": [{"limit_id": uuid7(), "kind": "BUDGET", "maximum": money("1000")}]}
        )
        .limits[0]
        .kind
        == "BUDGET"
    )
    changes: list[dict[str, Any]] = [
        {"requires_customer": False},
        {"requires_customer": 1},
        {"customer_binding": "NAMED_CUSTOMER", "requires_customer": False},
        {"limits": base["limits"] * 2},
        {"issued_codes": ["SECRET"]},
        {"starts_at": "2026-09-01"},
        {"ends_at": "2026-08-01T00:00:00Z"},
        {"limits": [{"limit_id": uuid7(), "kind": "TOTAL_USES", "maximum": True}]},
    ]
    for change in changes:
        with pytest.raises(ValidationError):
            CouponProgramTerms.model_validate({**base, **change})


def test_stack_policy_is_explicit_ordered_and_cannot_price_incomparable_gifts() -> None:
    groups = [
        {"group_id": uuid7(), "stage": stage, "selection": "PRIORITY", "changes_basket": False}
        for stage in ("PRODUCT_SCHEME", "BASKET", "MANUAL")
    ]
    pair = {"earlier_group_id": groups[0]["group_id"], "later_group_id": groups[1]["group_id"]}
    base = {"groups": groups, "maximum_applied": 3, "permissions": [pair]}
    assert len(StackPolicyTerms.model_validate(base).permissions) == 1
    assert StackPolicyTerms.model_validate({**base, "permissions": []}).permissions == ()
    for change in [
        {"groups": groups * 2},
        {"groups": list(reversed(groups))},
        {"permissions": [pair, pair]},
        {"permissions": [{**pair, "later_group_id": uuid7()}]},
        {"permissions": [{**pair, "later_group_id": pair["earlier_group_id"]}]},
        {"groups": [{**groups[0], "changes_basket": True, "selection": "BEST_SINGLE"}]},
    ]:
        with pytest.raises(ValidationError):
            StackPolicyTerms.model_validate({**base, **change})


def test_same_item_buy_get_requires_one_identical_sku_and_unit() -> None:
    item_id, other_id, unit_id = uuid7(), uuid7(), uuid7()
    benefit = {
        "kind": "BUY_GET",
        "qualifying": {"quantity": "10", "unit_revision_id": unit_id},
        "reward": {"quantity": "1", "unit_revision_id": unit_id},
        "reward_percent": "100",
        "pool": "SAME_ITEM",
        "reward_item_ids": [item_id],
        "selection": "LOWEST_REGULAR_UNIT_PRICE",
        "maximum_repeats": 10,
    }
    definition = terms(benefit)
    definition["condition_groups"] = [
        {"selectors": [{"dimension": "SKU", "mode": "INCLUDE", "ids": [item_id]}]}
    ]
    stack = StackPolicyTerms.model_validate(
        {
            "groups": [
                {
                    "group_id": definition["stack_group_id"],
                    "stage": "PRODUCT_SCHEME",
                    "selection": "PRIORITY",
                    "changes_basket": True,
                }
            ],
            "maximum_applied": 1,
        }
    )
    assert same_item_deal_profile(PromotionTerms.model_validate(definition), stack).item_ids == {
        item_id
    }
    general = PromotionTerms.model_validate(
        {**definition, "benefit": {**benefit, "reward_item_ids": [item_id, other_id]}}
    )
    assert isinstance(general.benefit, BuyGetBenefit)
    assert general.benefit.pool == "SAME_ITEM"
    # General authoring stays broader than this runtime profile.
    manual_id = uuid7()
    with_manual = StackPolicyTerms.model_validate(
        {
            "groups": [
                stack.groups[0].model_dump(),
                {
                    "group_id": manual_id,
                    "stage": "MANUAL",
                    "selection": "PRIORITY",
                    "changes_basket": False,
                },
            ],
            "permissions": [
                {"earlier_group_id": definition["stack_group_id"], "later_group_id": manual_id}
            ],
            "maximum_applied": 2,
        }
    )
    assert same_item_deal_profile(
        PromotionTerms.model_validate(definition), with_manual
    ).manual_stacking
    capped_stack = StackPolicyTerms.model_validate(
        {**with_manual.model_dump(), "maximum_applied": 1}
    )
    assert not same_item_deal_profile(
        PromotionTerms.model_validate(definition), capped_stack
    ).manual_stacking
    invalid = [
        {**benefit, "reward_item_ids": [item_id, other_id]},
        {**benefit, "reward": {"quantity": "1", "unit_revision_id": uuid7()}},
    ]
    for altered in invalid:
        with pytest.raises(ValidationFailedError, match="same-item"):
            same_item_deal_profile(
                PromotionTerms.model_validate({**definition, "benefit": altered}), stack
            )
    for groups in (
        [{"selectors": [{"dimension": "SKU", "mode": "INCLUDE", "ids": [other_id]}]}],
        [{"minimum_spend": money()}],
    ):
        with pytest.raises(ValidationFailedError, match="same-item"):
            same_item_deal_profile(
                PromotionTerms.model_validate({**definition, "condition_groups": groups}), stack
            )
