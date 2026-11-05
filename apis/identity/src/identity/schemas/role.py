"""Request and response schemas for roles and role assignments.

Permissions are code, roles are data (CLAUDE.md invariant 13): a role's ``permissions``
are catalogue keys validated on write, and the ``scope_id`` on an assignment speaks
``null`` for tenant scope on the wire — the ``SCOPE_ALL`` sentinel never crosses the
boundary (docs/identity-db-plan.md §2).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator

from identity.schemas.base import PageMeta, StrictModel


class RoleCreate(StrictModel):
    key: str = Field(min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]{2,59}$")
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    scope_hint: str | None = Field(default=None, max_length=20)
    permissions: list[str] = Field(min_length=1)


class RoleUpdate(StrictModel):
    nonnullable = frozenset(["name", "permissions"])

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    scope_hint: str | None = Field(default=None, max_length=20)
    #: When present, replaces the whole permission set — re-run through the composition
    #: guard, so a clerk cannot add a permission they do not hold to a role they edit.
    permissions: list[str] | None = Field(default=None, min_length=1)


class RoleClone(StrictModel):
    key: str = Field(min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]{2,59}$")
    name: str | None = Field(default=None, min_length=1, max_length=150)


class RoleListItem(StrictModel):
    id: uuid.UUID
    key: str
    name: str
    is_system: bool
    scope_hint: str | None
    is_active: bool
    updated_at: dt.datetime


class RoleDetail(StrictModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    scope_hint: str | None
    cloned_from_role_id: uuid.UUID | None
    is_active: bool
    permissions: list[str]
    created_at: dt.datetime
    updated_at: dt.datetime


class RolePage(StrictModel):
    items: list[RoleListItem]
    page: PageMeta


class RoleComposed(StrictModel):
    """A role plus any separation-of-duties pairs the composition holds both halves of.

    Returned (not rejected) for a tenant role: a small business may legitimately need
    one person to both raise and approve (docs/roles-permissions.md §1.4). The client
    surfaces the warning; the pairs are also recorded as an ``admin`` audit event.
    """

    role: RoleDetail
    separation_of_duties_warnings: list[list[str]]


class AssignmentValidity(StrictModel):
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to must be on or after valid_from (inclusive)")
        return self


class AssignmentRegrant(AssignmentValidity):
    reason: str = Field(min_length=1, max_length=500)


class AssignmentCreate(AssignmentValidity):
    subject_type: Literal["user", "user_group"]
    subject_id: uuid.UUID
    role_id: uuid.UUID
    scope_type: Literal["tenant", "company", "department"]
    #: ``null`` at tenant scope; a company id at company scope.
    scope_id: uuid.UUID | None = None
    grant_reason: str | None = Field(default=None, max_length=500)
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class AssignmentItem(StrictModel):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    role_id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID | None
    is_active: bool
    valid_from: dt.date
    valid_to: dt.date | None
    granted_by: uuid.UUID | None
    grant_reason: str | None
    created_at: dt.datetime
    # Directory labels are optional and independently authorized. They never widen
    # access to tenant profiles or organisation objects through role.read.
    role_name: str | None = None
    subject_label: str | None = None
    scope_label: str | None = None


class AssignmentCheck(StrictModel):
    allowed: Literal[True] = True


class AssignmentPage(StrictModel):
    items: list[AssignmentItem]
    page: PageMeta


class RevokeRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=500)


class PermissionCatalogue(StrictModel):
    permissions: list[str]
