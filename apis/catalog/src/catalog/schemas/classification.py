"""Classification input requiredness, protected projections and list contracts."""

import datetime as dt
import json
import uuid
from typing import Any, Literal

from billing_platform.custom_query import CustomPredicate
from billing_platform.errors import ValidationFailedError
from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from catalog.schemas.units import ExpectedVersion, UnitCreate

Kind = Literal["GOODS", "SERVICE", "BOTH"]
MembershipMode = Literal["SINGLE", "MULTIPLE"]


class MasterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        return UnitCreate.meaningful_label(value)


class GroupCreate(MasterInput):
    allowed_kind: Kind = "BOTH"
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    parent_group_id: uuid.UUID | None = None
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))


class SchemeCreate(MasterInput):
    membership_mode: MembershipMode
    # Requiredness is enabled through the reviewed transition, after impact checks.


class CategoryCreate(MasterInput):
    scheme_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)


class MasterUpdate(ExpectedVersion):
    code: str | None = Field(
        default=None, min_length=1, max_length=30, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$"
    )
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def no_null_labels(self) -> "MasterUpdate":
        if any(
            key in self.model_fields_set and getattr(self, key) is None for key in ("code", "name")
        ):
            raise ValueError("master labels cannot be cleared")
        return self


class GroupUpdate(MasterUpdate):
    allowed_kind: Kind | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)


class SchemeUpdate(MasterUpdate):
    membership_mode: MembershipMode | None = None


class CategoryUpdate(MasterUpdate):
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)


class GroupReparent(ExpectedVersion):
    expected_generation: int = Field(ge=1, strict=True)
    parent_group_id: uuid.UUID | None
    effective_from: dt.date = Field(ge=dt.date(1000, 1, 1))


class CategoryReparent(ExpectedVersion):
    expected_generation: int = Field(ge=1, strict=True)
    parent_id: uuid.UUID | None


class MasterListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    is_active: bool | None = None
    row_version: int | None = None


class GroupListItem(MasterListItem):
    allowed_kind: Kind | None = None


class SchemeListItem(MasterListItem):
    membership_mode: MembershipMode | None = None
    is_required: bool | None = None


class CategoryListItem(MasterListItem):
    scheme_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None


class DetailFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    policy_generation: int


class GroupDetail(GroupListItem, DetailFields):
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class SchemeDetail(SchemeListItem, DetailFields):
    pass


class CategoryDetail(CategoryListItem, DetailFields):
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class MasterQuery(ListQuery):
    custom_filters: str | None = Field(default=None, max_length=4096)

    def predicates(self) -> list[CustomPredicate]:
        if self.custom_filters is None:
            return []
        try:
            raw = json.loads(self.custom_filters)
            if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
                raise ValueError("bounded predicates required")
            return [CustomPredicate.model_validate(item) for item in raw]
        except ValueError as exc:
            raise ValidationFailedError("invalid custom filter query") from exc

    is_active: bool | None = None
    code: str | None = Field(default=None, min_length=1, max_length=30)


class GroupQuery(MasterQuery):
    allowed_kind: Kind | None = None


class SchemeQuery(MasterQuery):
    membership_mode: MembershipMode | None = None


class CategoryQuery(MasterQuery):
    scheme_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None


class GroupParentListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    group_id: uuid.UUID | None = None
    parent_group_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class GroupParentQuery(ListQuery):
    valid_at: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


class ChildrenQuery(MasterQuery):
    """Browsing one level of a dated hierarchy: the date is required, never defaulted.

    A default would answer "children today" to a question asked about a past reporting
    period, which is the one answer a dated hierarchy exists to avoid.
    """

    valid_at: dt.date = Field(ge=dt.date(1000, 1, 1))


class GroupChildrenQuery(GroupQuery, ChildrenQuery):
    pass
