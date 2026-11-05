"""Stack definition form controls; field policy is enforced by the command layer."""

from catalog.models.promotion_authoring import PROMOTION_AUTHORING_MODELS
from catalog.models.promotions import (
    PromotionStackGroup,
    PromotionStackPermission,
    PromotionStackPolicy,
)
from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

PUBLISHED_MODELS = (PromotionStackPolicy, PromotionStackGroup, PromotionStackPermission)
ALL_MODELS = (*PROMOTION_AUTHORING_MODELS, *PUBLISHED_MODELS)

ENTITIES = frozenset("catalog." + model.__tablename__ for model in ALL_MODELS)
PUBLISHED = frozenset("catalog." + model.__tablename__ for model in PUBLISHED_MODELS)
PUBLISH_PERMISSIONS = {entity: "promotion_stack_policy.publish" for entity in ENTITIES}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in ENTITIES:
        return None
    labels = {
        "code": "Policy code",
        "maximum_applied": "Maximum applied offers",
        "change_reason": "Change reason",
        "stage": "Application stage",
        "selection": "Selection rule",
        "changes_basket": "Changes physical quantities",
        "include_reward_units": "Allow later offers on reward units",
    }
    label = labels.get(key, key.replace("_", " ").capitalize())
    if key in {"earlier_group_id", "later_group_id"}:
        return ConfigurationControl(
            kind="reference",
            label="Earlier group" if key == "earlier_group_id" else "Later group",
            reference_source="stack-groups",
        )
    if key in {"code", "change_reason"}:
        return ConfigurationControl(
            kind="text", label=label, max_length=30 if key == "code" else 500
        )
    if key == "maximum_applied":
        return ConfigurationControl(kind="integer", label=label, minimum=1, maximum=10)
    if key in {"changes_basket", "include_reward_units"}:
        return ConfigurationControl(kind="boolean", label=label)
    values = {
        "stage": (
            ("PRODUCT_SCHEME", "Product / scheme"),
            ("BASKET", "Basket"),
            ("MANUAL", "Manual discount"),
        ),
        "selection": (
            ("PRIORITY", "Priority"),
            ("BEST_SINGLE", "Best single comparable benefit"),
            ("CUSTOMER_CHOICE", "Customer choice"),
        ),
    }.get(key)
    if values:
        return ConfigurationControl(
            kind="select",
            label=label,
            choices=[ConfigurationChoice(value=value, label=text) for value, text in values],
        )
    return None
