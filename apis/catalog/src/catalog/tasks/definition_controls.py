"""Native commercial-definition editor hints; never an authorization source."""

from catalog.schemas.field_metadata import ConfigurationChoice, ConfigurationControl

ENTITIES = frozenset({"catalog.promotion_limit_definition", "catalog.promotion_limit_revision"})
REVISIONS = {"catalog.promotion_limit_revision": "definition_id"}
PUBLISH_PERMISSIONS = {"catalog.promotion_limit_revision": "promotion_limit.publish"}
GENERATED = frozenset(
    {
        "revision",
        "row_version",
        "published_at",
        "published_source_version",
        "publication_generation",
    }
)
CHOICES = {
    "scope_kind": (
        ("CAMPAIGN", "Campaign"),
        ("PROMOTION", "Promotion"),
        ("PROGRAM", "Coupon program"),
    ),
    "metric": (
        ("TOTAL_USES", "Total uses"),
        ("PER_CUSTOMER_USES", "Uses per customer"),
        ("PER_ORDER_USES", "Uses per order"),
        ("REWARD_UNITS", "Reward quantity"),
        ("BUDGET", "Net benefit budget"),
    ),
    "period_basis": (
        ("LIFETIME", "Lifetime"),
        ("DAY", "Calendar day"),
        ("MONTH", "Calendar month"),
        ("YEAR", "Calendar year"),
        ("ORDER", "Per order"),
    ),
}


def control(entity: str, key: str) -> ConfigurationControl | None:
    if entity not in ENTITIES:
        return None
    label = {
        "scope_kind": "Quota scope",
        "metric": "Quota measure",
        "period_basis": "Usage period",
        "timezone": "Period timezone",
        "unit_id": "Reward count unit",
        "currency": "Budget currency",
        "maximum_count": "Maximum uses",
        "maximum_quantity": "Maximum reward quantity",
        "maximum_amount": "Maximum net benefit",
    }.get(key, key.replace("_", " ").capitalize())
    if key in CHOICES:
        return ConfigurationControl(
            kind="select",
            label=label,
            choices=[ConfigurationChoice(value=value, label=text) for value, text in CHOICES[key]],
        )
    if key in {"code", "name", "change_reason", "timezone", "currency", "maximum_count"}:
        return ConfigurationControl(
            kind="text",
            label=label,
            nullable=key in {"currency", "maximum_count"},
            max_length={
                "code": 30,
                "name": 100,
                "change_reason": 500,
                "timezone": 64,
                "currency": 3,
                "maximum_count": 19,
            }[key],
        )
    if key in {"maximum_quantity", "maximum_amount"}:
        return ConfigurationControl(kind="decimal", label=label, nullable=True, max_length=20)
    if key == "unit_id":
        return ConfigurationControl(
            kind="reference", label=label, reference_source="units", nullable=True
        )
    if key == "is_active":
        return ConfigurationControl(kind="boolean", label=label)
    return None
