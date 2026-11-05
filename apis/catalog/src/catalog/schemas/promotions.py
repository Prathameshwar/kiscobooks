"""Typed Catalog promotion-definition contract; no basket or coupon execution."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal, Self

from billing_platform.exact import exact_decimal
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

type Exact = Annotated[Decimal, BeforeValidator(exact_decimal)]
type Positive = Annotated[Exact, Field(gt=0)]
type Percent = Annotated[Exact, Field(gt=0, le=100)]
type Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
type AmountBasis = Literal["NET_EXCL_TAX", "GROSS_INCL_TAX"]
type RealId = Annotated[uuid.UUID, BeforeValidator(lambda value: non_nil_id(value))]


def non_nil_id(value: object) -> uuid.UUID:
    if not isinstance(value, uuid.UUID | str):
        raise ValueError("UUID identity required")
    identifier = value if isinstance(value, uuid.UUID) else uuid.UUID(value)
    if identifier.int == 0:
        raise ValueError("non-nil identity required")
    return identifier


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MoneyDefinition(Definition):
    amount: Positive
    currency: Currency
    basis: AmountBasis


class QuantityDefinition(Definition):
    quantity: Positive
    unit_revision_id: RealId


class NativeSelector(Definition):
    dimension: Literal[
        "CUSTOMER",
        "CUSTOMER_TYPE",
        "PRICE_LEVEL",
        "SALES_CHANNEL",
        "WAREHOUSE",
        "PRODUCT_TYPE",
        "SKU",
        "FAMILY",
        "GROUP",
        "CATEGORY",
        "BRAND",
        "APPROVED_MANUFACTURER",
        "VERIFIED_LOT",
    ]
    mode: Literal["INCLUDE", "EXCLUDE"]
    ids: tuple[RealId, ...] = Field(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def distinct(cls, values: tuple[uuid.UUID, ...]) -> tuple[uuid.UUID, ...]:
        if len(values) != len(set(values)):
            raise ValueError("selector identities must be distinct")
        return values


class AttributeTarget(Definition):
    attribute_id: RealId
    option_ids: tuple[RealId, ...] = Field(min_length=1, max_length=100)
    mode: Literal["INCLUDE", "EXCLUDE"]

    @field_validator("option_ids")
    @classmethod
    def distinct(cls, values: tuple[uuid.UUID, ...]) -> tuple[uuid.UUID, ...]:
        return NativeSelector.distinct(values)


class ConditionGroup(Definition):
    selectors: tuple[NativeSelector, ...] = Field(default=(), max_length=20)
    attributes: tuple[AttributeTarget, ...] = Field(default=(), max_length=20)
    item_kinds: tuple[Literal["GOODS", "SERVICE"], ...] = Field(default=(), max_length=2)
    minimum_spend: MoneyDefinition | None = None
    minimum_quantity: QuantityDefinition | None = None

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        keys = [(row.dimension, row.mode) for row in self.selectors]
        attributes = [(row.attribute_id, row.mode) for row in self.attributes]
        if (
            len(set(keys)) != len(keys)
            or len(set(attributes)) != len(attributes)
            or len(set(self.item_kinds)) != len(self.item_kinds)
        ):
            raise ValueError("duplicate condition dimensions")
        return self


class PercentageBenefit(Definition):
    kind: Literal["LINE_PERCENT", "BASKET_PERCENT"]
    percent: Percent
    maximum_benefit: MoneyDefinition | None = None


class FixedBenefit(Definition):
    kind: Literal["LINE_FIXED", "BASKET_FIXED"]
    value: MoneyDefinition
    application: Literal["PER_UNIT", "PER_LINE", "PER_BASKET"]

    @model_validator(mode="after")
    def compatible_scope(self) -> Self:
        if (self.kind == "BASKET_FIXED") != (self.application == "PER_BASKET"):
            raise ValueError("fixed benefit application differs from its stage")
        return self


class QuantityBenefit(Definition):
    kind: Literal["QUANTITY"] = "QUANTITY"
    qualifying: QuantityDefinition
    percent: Percent
    maximum_repeats: int = Field(strict=True, ge=1, le=1000)


class BuyGetBenefit(Definition):
    kind: Literal["BUY_GET"] = "BUY_GET"
    qualifying: QuantityDefinition
    reward: QuantityDefinition
    reward_percent: Percent
    pool: Literal["SAME_ITEM", "CROSS_ITEM"]
    reward_item_ids: tuple[RealId, ...] = Field(min_length=1, max_length=100)
    selection: Literal["LOWEST_REGULAR_UNIT_PRICE", "CUSTOMER_CHOICE"]
    maximum_repeats: int = Field(strict=True, ge=1, le=1000)

    @field_validator("reward_item_ids")
    @classmethod
    def distinct(cls, values: tuple[uuid.UUID, ...]) -> tuple[uuid.UUID, ...]:
        return NativeSelector.distinct(values)


class BundleComponent(Definition):
    item_id: RealId
    quantity: QuantityDefinition


class BundleBenefit(Definition):
    kind: Literal["BUNDLE_PRICE"] = "BUNDLE_PRICE"
    components: tuple[BundleComponent, ...] = Field(min_length=1, max_length=100)
    target: MoneyDefinition
    maximum_repeats: int = Field(strict=True, ge=1, le=1000)

    @model_validator(mode="after")
    def distinct_components(self) -> Self:
        keys = [(row.item_id, row.quantity.unit_revision_id) for row in self.components]
        if len(keys) != len(set(keys)):
            raise ValueError("bundle component must have one exact quantity")
        return self


class MixMatchBenefit(Definition):
    kind: Literal["MIX_MATCH"] = "MIX_MATCH"
    pool_item_ids: tuple[RealId, ...] = Field(min_length=1, max_length=100)
    choose_quantity: QuantityDefinition
    target: MoneyDefinition
    maximum_repeats: int = Field(strict=True, ge=1, le=1000)

    @field_validator("pool_item_ids")
    @classmethod
    def distinct(cls, values: tuple[uuid.UUID, ...]) -> tuple[uuid.UUID, ...]:
        return NativeSelector.distinct(values)


class GiftBenefit(Definition):
    kind: Literal["GIFT"] = "GIFT"
    reward: QuantityDefinition
    reward_item_ids: tuple[RealId, ...] = Field(min_length=1, max_length=100)
    selection: Literal["LOWEST_REGULAR_UNIT_PRICE", "CUSTOMER_CHOICE"]
    maximum_repeats: int = Field(strict=True, ge=1, le=1000)

    @field_validator("reward_item_ids")
    @classmethod
    def distinct(cls, values: tuple[uuid.UUID, ...]) -> tuple[uuid.UUID, ...]:
        return NativeSelector.distinct(values)


type Benefit = Annotated[
    PercentageBenefit
    | FixedBenefit
    | QuantityBenefit
    | BuyGetBenefit
    | BundleBenefit
    | MixMatchBenefit
    | GiftBenefit,
    Field(discriminator="kind"),
]


class PromotionTerms(Definition):
    currency: Currency
    eligible_price_level_ids: tuple[RealId, ...] = Field(min_length=1, max_length=100)
    selection_mode: Literal["SNAPSHOT_ON_PUBLISH", "CURRENT_AT_EVALUATION"]
    condition_groups: tuple[ConditionGroup, ...] = Field(min_length=1, max_length=20)
    benefit: Benefit
    trigger: Literal["AUTOMATIC", "COUPON"]
    starts_at: dt.datetime
    ends_at: dt.datetime
    timezone: str = Field(min_length=1, max_length=64)
    stack_policy_revision_id: RealId
    stack_group_id: RealId
    return_policy_revision_id: RealId
    priority: int = Field(strict=True, ge=0, le=32767)

    @field_validator("eligible_price_level_ids")
    @classmethod
    def distinct(cls, values: tuple[uuid.UUID, ...]) -> tuple[uuid.UUID, ...]:
        return NativeSelector.distinct(values)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("promotion instants require offsets")
        return value.astimezone(dt.UTC)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("unknown IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("promotion interval must be nonempty")
        amounts = [
            group.minimum_spend
            for group in self.condition_groups
            if group.minimum_spend is not None
        ]
        if isinstance(self.benefit, FixedBenefit):
            amounts.append(self.benefit.value)
        elif isinstance(self.benefit, BundleBenefit | MixMatchBenefit):
            amounts.append(self.benefit.target)
        elif (
            isinstance(self.benefit, PercentageBenefit) and self.benefit.maximum_benefit is not None
        ):
            amounts.append(self.benefit.maximum_benefit)
        if any(amount.currency != self.currency for amount in amounts):
            raise ValueError("promotion amounts require a consistent currency")
        if self.benefit.kind in {"BASKET_PERCENT", "BASKET_FIXED"} and any(
            group.minimum_spend is None for group in self.condition_groups
        ):
            raise ValueError("each basket qualification alternative requires eligible spend")
        if isinstance(self.benefit, GiftBenefit) and any(
            group.minimum_spend is None and group.minimum_quantity is None
            for group in self.condition_groups
        ):
            raise ValueError(
                "each gift qualification alternative requires a spend or quantity threshold"
            )
        return self


class CountLimit(Definition):
    limit_id: RealId
    kind: Literal["TOTAL_USES", "PER_CUSTOMER_USES", "PER_ORDER_USES"]
    maximum: int = Field(strict=True, ge=1, le=2**63 - 1)


class BudgetLimit(Definition):
    limit_id: RealId
    kind: Literal["BUDGET"] = "BUDGET"
    maximum: MoneyDefinition


type PromotionLimit = Annotated[CountLimit | BudgetLimit, Field(discriminator="kind")]


class CouponProgramTerms(Definition):
    promotion_id: RealId
    code_mode: Literal["SHARED_PUBLIC", "UNIQUE_ISSUED"]
    code_case: Literal["SENSITIVE", "INSENSITIVE"]
    customer_binding: Literal["NONE", "NAMED_CUSTOMER"]
    requires_customer: StrictBool = False
    starts_at: dt.datetime
    ends_at: dt.datetime
    limits: tuple[PromotionLimit, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.starts_at.tzinfo is None
            or self.ends_at.tzinfo is None
            or self.ends_at <= self.starts_at
        ):
            raise ValueError("coupon interval requires ordered aware instants")
        if self.customer_binding == "NAMED_CUSTOMER" and not self.requires_customer:
            raise ValueError("named binding requires customer identity")
        ids = [limit.limit_id for limit in self.limits]
        kinds = [limit.kind for limit in self.limits]
        if len(set(ids)) != len(ids) or len(set(kinds)) != len(kinds):
            raise ValueError("limit identities and kinds must be unique")
        if (
            any(limit.kind == "PER_CUSTOMER_USES" for limit in self.limits)
            and not self.requires_customer
        ):
            raise ValueError("customer usage limits require an authoritative customer")
        return self


class StackGroup(Definition):
    group_id: RealId
    stage: Literal["PRODUCT_SCHEME", "BASKET", "MANUAL"]
    selection: Literal["PRIORITY", "BEST_SINGLE", "CUSTOMER_CHOICE"]
    changes_basket: StrictBool

    @model_validator(mode="after")
    def comparable_baskets(self) -> Self:
        if self.changes_basket and self.selection == "BEST_SINGLE":
            raise ValueError("different gift or bundle baskets have no implicit cash equivalence")
        return self


class StackPermission(Definition):
    earlier_group_id: RealId
    later_group_id: RealId
    include_reward_units: StrictBool = False


class StackPolicyTerms(Definition):
    # No permission pair means no stacking, including manual discounts.
    groups: tuple[StackGroup, ...] = Field(min_length=1, max_length=20)
    permissions: tuple[StackPermission, ...] = Field(default=(), max_length=190)
    maximum_applied: int = Field(strict=True, ge=1, le=10)

    @model_validator(mode="after")
    def ordered_permissions(self) -> Self:
        positions = {group.group_id: index for index, group in enumerate(self.groups)}
        if len(positions) != len(self.groups):
            raise ValueError("stack groups must be unique")
        stage_order = {"PRODUCT_SCHEME": 0, "BASKET": 1, "MANUAL": 2}
        stages = [stage_order[group.stage] for group in self.groups]
        if stages != sorted(stages):
            raise ValueError("stack stages must preserve product, basket, manual order")
        pairs = set()
        for permission in self.permissions:
            pair = permission.earlier_group_id, permission.later_group_id
            if (
                any(group_id not in positions for group_id in pair)
                or positions[pair[0]] >= positions[pair[1]]
                or pair in pairs
            ):
                raise ValueError("stack permission must name one unique forward pair")
            pairs.add(pair)
        return self
