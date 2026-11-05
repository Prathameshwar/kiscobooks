"""Location grouping specs and the dated member rollup.

Both masters ride the shared classification pipeline, and the group's dated parent link
rides the same ``DatedEdge`` machinery as an item group's: a rollup is only worth having if
"which locations were under this group in March" still answers what it answered in March
(docs/catalog-warehouses.md §3).
"""

import datetime as dt
import uuid
from collections import deque

from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.warehouse_groups import (
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouses import Warehouse, WarehouseBin
from catalog.schemas.warehouse_groups import (
    BinCreate,
    BinDetail,
    BinListItem,
    GroupMemberQuery,
    WarehouseGroupCreate,
    WarehouseGroupDetail,
    WarehouseGroupListItem,
)
from catalog.tasks.classification import Classification, DatedEdge, bounded_rows, list_rows
from catalog.tasks.field_context import load_field_context
from catalog.tasks.warehouses import WAREHOUSE

WAREHOUSE_GROUP = Classification(
    WarehouseGroup,
    "catalog.warehouse_group",
    "warehouse_group",
    WarehouseGroupCreate,
    WarehouseGroupDetail,
    WarehouseGroupListItem,
    frozenset({"code", "is_active"}),
    hierarchy=DatedEdge(
        WarehouseGroupParent,
        "catalog.warehouse_group_parent",
        "group_id",
        "parent_group_id",
        WarehouseGroup,
    ),
)
WAREHOUSE_BIN = Classification(
    WarehouseBin,
    "catalog.warehouse_bin",
    "warehouse_bin",
    BinCreate,
    BinDetail,
    BinListItem,
    frozenset({"code", "is_active", "warehouse_id"}),
)


def descendants(
    edges: list[WarehouseGroupParent], root: uuid.UUID, valid_at: dt.date
) -> set[uuid.UUID]:
    """The group and everything reporting to it on one date.

    Breadth-first over the intervals in force on that date only, so a group moved out of
    the tree last month stops being part of the old parent's rollup from that date and
    stays part of it for every date before.
    """
    children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for edge in edges:
        if edge.parent_group_id is None or edge.valid_from > valid_at:
            continue
        if edge.valid_to is not None and edge.valid_to < valid_at:
            continue
        children.setdefault(edge.parent_group_id, []).append(edge.group_id)
    reached = {root}
    frontier = deque([root])
    while frontier:
        for child in children.get(frontier.popleft(), ()):
            # The hierarchy is cycle-checked on write; the visited set keeps a corrupted
            # one from spinning here rather than trusting that check from a read path.
            if child not in reached:
                reached.add(child)
                frontier.append(child)
    return reached


async def list_members(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    group_id: uuid.UUID,
    query: GroupMemberQuery,
    secret: bytes,
) -> Page[BaseModel]:
    """Locations under a group and its descendants, as the hierarchy stood on a date.

    Two permissions, because two things are being read: ``warehouse_group.read`` for the
    composition and ``warehouse.read`` for the locations themselves, the latter enforced by
    the shared list path this delegates to. Membership grants neither.
    """
    context = await load_field_context(db, actor, company, "catalog.warehouse_group_assignment")
    if not {"warehouse_id", "group_id", "valid_from", "valid_to"} <= context.readable():
        raise PermissionDeniedError("member browsing requires readable membership fields")
    await company_object(db, WarehouseGroup, group_id, company_id=company)
    groups = descendants(
        await bounded_rows(db, WarehouseGroupParent, company), group_id, query.valid_at
    )
    membership = WarehouseGroupAssignment
    relation = (
        select(membership.id)
        .where(
            membership.company_id == company,
            membership.warehouse_id == Warehouse.id,
            membership.group_id.in_(groups),
            membership.valid_from <= query.valid_at,
            or_(membership.valid_to.is_(None), membership.valid_to >= query.valid_at),
        )
        .exists()
    )
    return await list_rows(
        db,
        actor,
        company,
        WAREHOUSE,
        query,
        secret,
        criterion=relation,
        cursor_resource="catalog.warehouse_group.members:" + str(group_id),
    )
