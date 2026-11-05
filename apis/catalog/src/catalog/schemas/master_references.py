"""Parent-nested reference inputs and bounded browse/resolve contracts."""

import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from catalog.domain.master_references import external_key, normalized_alias
from catalog.schemas.classification import DetailFields

MasterEntity = Literal[
    "catalog.unit_of_measure",
    "catalog.pack_type",
    "catalog.item_group",
    "catalog.category_scheme",
    "catalog.item_category",
    "catalog.product_type",
    "catalog.brand",
    "catalog.brand_series",
    "catalog.manufacturer",
    "catalog.manufacturer_site",
    "catalog.attribute_definition",
    "catalog.attribute_option",
    "catalog.attribute_set",
    "catalog.identifier_profile",
    "catalog.inventory_profile_template",
    "catalog.warranty_policy",
    "catalog.return_policy",
    "catalog.handling_profile",
    "catalog.tax_category",
    "catalog.tax_rule",
    "catalog.tax_classification",
]


class AliasCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str = Field(min_length=1, max_length=100)

    @field_validator("alias")
    @classmethod
    def valid_alias(cls, value: str) -> str:
        return normalized_alias(value)[0]


class ExternalKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_namespace: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    external_key: str = Field(min_length=1, max_length=200)

    @field_validator("external_key")
    @classmethod
    def exact_key(cls, value: str) -> str:
        return external_key(value)


class ReferenceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    entity_type: MasterEntity | None = None
    target_id: uuid.UUID | None = None
    is_active: bool | None = None
    row_version: int | None = None


class AliasListItem(ReferenceListItem):
    alias: str | None = None
    canonical_value: str | None = None
    normalization_version: int | None = None


class ExternalKeyListItem(ReferenceListItem):
    source_namespace: str | None = None
    external_key: str | None = None


class AliasDetail(AliasListItem, DetailFields):
    pass


class ExternalKeyDetail(ExternalKeyListItem, DetailFields):
    pass


class AliasQuery(ListQuery):
    is_active: bool | None = None


class ExternalKeyQuery(ListQuery):
    is_active: bool | None = None
    source_namespace: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    external_key: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def scoped_key(self) -> "ExternalKeyQuery":
        if self.external_key is not None:
            external_key(self.external_key)
            if self.source_namespace is None:
                raise ValueError("an exact external key filter requires its source namespace")
        return self
