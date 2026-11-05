"""Schemas for the org structure: departments, user groups, memberships."""

from __future__ import annotations

import datetime as dt
import re
import uuid

from pydantic import Field, ValidationInfo, field_validator

from identity.schemas.base import PageMeta, StrictModel

# --- department ---------------------------------------------------------------


class OrgInput(StrictModel):
    @field_validator("code", "name", "description", "cost_centre_code", check_fields=False)
    @classmethod
    def printable_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        if re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("use printable characters")
        text = value.strip()
        if not text and info.field_name in {"code", "name"}:
            raise ValueError("must not be blank")
        return text or None


class DepartmentCreate(OrgInput):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    parent_id: uuid.UUID | None = None
    cost_centre_code: str | None = Field(default=None, max_length=30)
    head_user_id: uuid.UUID | None = None


class DepartmentUpdate(OrgInput):
    nonnullable = frozenset(["code", "name"])

    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    cost_centre_code: str | None = Field(default=None, max_length=30)
    head_user_id: uuid.UUID | None = None


class DepartmentReparent(StrictModel):
    #: ``null`` makes the department a root.
    parent_id: uuid.UUID | None = None


class DepartmentItem(StrictModel):
    id: uuid.UUID
    company_id: uuid.UUID
    parent_id: uuid.UUID | None
    code: str
    name: str
    cost_centre_code: str | None
    head_user_id: uuid.UUID | None
    path: str
    is_active: bool


class DepartmentListItem(StrictModel):
    id: uuid.UUID
    company_id: uuid.UUID
    parent_id: uuid.UUID | None
    code: str
    name: str
    path: str
    is_active: bool


# --- user group ---------------------------------------------------------------


class UserGroupCreate(OrgInput):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)


class UserGroupItem(StrictModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool


class UserGroupListItem(StrictModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class GroupMemberAdd(StrictModel):
    user_id: uuid.UUID


class GroupMemberItem(StrictModel):
    id: uuid.UUID
    user_group_id: uuid.UUID
    user_id: uuid.UUID
    created_at: dt.datetime


class GroupMemberListItem(GroupMemberItem):
    #: Names are omitted unless the actor has tenant-wide user.read.
    display_name: str | None = None


# --- membership ---------------------------------------------------------------


class MembershipCreate(StrictModel):
    user_id: uuid.UUID
    department_id: uuid.UUID | None = None
    is_primary: bool = False
    started_on: dt.date | None = None


class MembershipItem(StrictModel):
    id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID
    department_id: uuid.UUID | None
    is_primary: bool
    started_on: dt.date | None
    ended_on: dt.date | None
    is_active: bool


class DepartmentPage(StrictModel):
    items: list[DepartmentListItem]
    page: PageMeta
