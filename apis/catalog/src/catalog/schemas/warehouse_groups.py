"""Location grouping, dated membership and bin contracts.

A group is a reporting dimension: nothing here names an operation, a permission or a
quantity, because a group grants none of those (docs/catalog-warehouses.md §3).
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from catalog.schemas.classification import (
    ChildrenQuery,
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.schemas.warehouses import WarehouseQuery


class WarehouseGroupCreate(MasterInput):
    """A group and the interval its parent link opens.

    ``valid_from`` is required and dated from the start: the hierarchy answers "who did
    this group report to on that date", and a create with no opening interval would leave
    a group whose history begins nowhere.
    """

    parent_group_id: uuid.UUID | None = None
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))


class WarehouseGroupUpdate(MasterUpdate):
    """Identity only. The parent link moves through the reviewed reparent action."""


class WarehouseGroupReparent(ExpectedVersion):
    """Appends a future interval; it never rewrites the one in force."""

    expected_generation: int = Field(ge=1, strict=True)
    parent_group_id: uuid.UUID | None
    effective_from: dt.date = Field(ge=dt.date(1000, 1, 1))


class WarehouseGroupListItem(MasterListItem):
    pass


class WarehouseGroupDetail(WarehouseGroupListItem, DetailFields):
    pass


class WarehouseGroupQuery(MasterQuery):
    pass


class WarehouseGroupChildrenQuery(WarehouseGroupQuery, ChildrenQuery):
    pass


class PrimaryGroupInput(ExpectedVersion):
    """One location's dated primary group.

    ``group_id`` may be ``null``, which closes the current membership and opens nothing:
    "no group" is the absence of an open interval, never a row pointing at nothing. A
    membership change grants and revokes no access to the location either way (§3).
    """

    expected_generation: int = Field(ge=1, strict=True)
    group_id: uuid.UUID | None
    effective_from: dt.date = Field(ge=dt.date(1000, 1, 1))


class GroupMemberQuery(WarehouseQuery):
    """Members roll up the group and its descendants as the hierarchy stood on a date."""

    valid_at: dt.date = Field(ge=dt.date(1000, 1, 1))


class BinCreate(MasterInput):
    """A subdivision of one location. The location is part of the bin's identity."""

    warehouse_id: uuid.UUID


class BinUpdate(MasterUpdate):
    """Label only. A bin cannot move to another location — that is a different bin."""


class BinListItem(MasterListItem):
    warehouse_id: uuid.UUID | None = None


class BinDetail(BinListItem, DetailFields):
    pass


class BinQuery(MasterQuery):
    warehouse_id: uuid.UUID | None = None


class WarehouseStructureContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    timezone: str
    business_date: dt.date
    policy_generation: int
    source_version: int


class WarehouseGroupAssignmentListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
