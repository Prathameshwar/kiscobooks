"""Display-brand defaults; technical identifiers and customer names are independent."""

PRODUCT_NAME = "KiscoBooks"
PUBLISHER_NAME = "Khushiyan Enterprise"
LEGACY_PRODUCT_NAMES = frozenset({"janso"})


def is_legacy_product_name(value: str | None) -> bool:
    return value is not None and value.strip().casefold() in LEGACY_PRODUCT_NAMES
