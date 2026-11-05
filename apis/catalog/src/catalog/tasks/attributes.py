"""Attribute masters use the existing native master pipeline."""

from catalog.models.attributes import AttributeDefinition, AttributeOption, AttributeSet
from catalog.schemas.attributes import (
    AttributeDefinitionCreate,
    AttributeDefinitionDetail,
    AttributeDefinitionListItem,
    AttributeOptionCreate,
    AttributeOptionDetail,
    AttributeOptionListItem,
    AttributeSetCreate,
    AttributeSetDetail,
    AttributeSetListItem,
)
from catalog.tasks.classification import Classification

ATTRIBUTE_DEFINITION = Classification(
    AttributeDefinition,
    "catalog.attribute_definition",
    "attribute_definition",
    AttributeDefinitionCreate,
    AttributeDefinitionDetail,
    AttributeDefinitionListItem,
    frozenset({"is_active", "code", "measurement_dimension", "value_type", "is_variant_capable"}),
)
ATTRIBUTE_OPTION = Classification(
    AttributeOption,
    "catalog.attribute_option",
    "attribute_option",
    AttributeOptionCreate,
    AttributeOptionDetail,
    AttributeOptionListItem,
    frozenset({"definition_id", "is_active", "value_type", "code"}),
)
ATTRIBUTE_SET = Classification(
    AttributeSet,
    "catalog.attribute_set",
    "attribute_set",
    AttributeSetCreate,
    AttributeSetDetail,
    AttributeSetListItem,
    frozenset({"is_active", "code"}),
)
