"""Non-stockholding location grouping: the group, its dated hierarchy and its membership.

A group is a reporting and organisational dimension, never a place. Nothing can be stored in
one, no document may select one, and — the rule this file exists to keep honest — membership
of a group **confers no access to its member locations** (docs/catalog-warehouses.md §3).
Access stays with the actor's own scope over each location, which is why no row here carries
a permission, a flag or a scope of any kind.

Both dated tables append and close intervals rather than rewriting them, so "which group did
this location report to on that date" keeps answering what it answered then.
"""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.classification import ClassificationMaster, HierarchyEdge
from catalog.models.commercial import master_constraints


class WarehouseGroup(ClassificationMaster):
    """A named grouping of stock locations. Carries no capability of its own.

    Deliberately just an identity and a lifecycle: every operation permission lives on the
    location's own policy revision, so a group cannot become a second place to grant one.
    """

    __tablename__ = "warehouse_group"
    __table_args__ = (*master_constraints("warehouse_group"), MARIADB_TABLE_ARGS)


class WarehouseGroupParent(HierarchyEdge):
    """The dated parent of one group. Same shape and rules as ``item_group_parent``."""

    __tablename__ = "warehouse_group_parent"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "group_id",
            "valid_from",
            name="uq_warehouse_group_parent_start",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["warehouse_group.tenant_id", "warehouse_group.company_id", "warehouse_group.id"],
            name="fk_warehouse_group_parent_group",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "parent_group_id"],
            ["warehouse_group.tenant_id", "warehouse_group.company_id", "warehouse_group.id"],
            name="fk_warehouse_group_parent_parent",
        ),
        Index(
            "ix_warehouse_group_parent_descendants",
            "tenant_id",
            "company_id",
            "parent_group_id",
            "valid_from",
            "id",
        ),
        # Short local names: the convention prefixes the table, and the usual
        # "<table>_<rule>" form would repeat a 22-character table name in every one.
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="dates"),
        CheckConstraint("valid_from >= '1000-01-01'", name="date_range"),
        CheckConstraint("parent_group_id IS NULL OR parent_group_id <> group_id", name="self"),
        MARIADB_TABLE_ARGS,
    )


class WarehouseGroupAssignment(IdMixin, TenantMixin, AuditMixin, Base):
    """One location's dated primary group.

    Primary and single on purpose: a location that reported to two groups at once would make
    every rollup double-count it. Membership is closed rather than deleted, and "no group" is
    the absence of an open interval — never a row pointing at nothing, which a rollup would
    have to guess about.
    """

    __tablename__ = "warehouse_group_assignment"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_warehouse_group_assignment_scope_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "warehouse_id",
            "valid_from",
            name="uq_warehouse_group_assignment_start",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "warehouse_id"],
            ["warehouse.tenant_id", "warehouse.company_id", "warehouse.id"],
            name="fk_warehouse_group_assignment_warehouse",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "group_id"],
            ["warehouse_group.tenant_id", "warehouse_group.company_id", "warehouse_group.id"],
            name="fk_warehouse_group_assignment_group",
        ),
        Index(
            "ix_warehouse_group_assignment_group",
            "tenant_id",
            "company_id",
            "group_id",
            "valid_from",
            "id",
        ),
        # Short local names, as in `warehouse_group_parent` above.
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="dates"),
        CheckConstraint("valid_from >= '1000-01-01'", name="date_range"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


WAREHOUSE_GROUP_MODELS = (WarehouseGroup, WarehouseGroupParent, WarehouseGroupAssignment)
