"""``department`` — a cost centre within a company, self-nesting.

docs/identity-schema.md §3.12, docs/org-model.md §2.4. A department is an org unit, a
default cost-centre target, and a *scope* an assignment can be narrowed to — it is **not**
an approval chain (org-model §5): reporting lines live on ``user.reporting_manager_id``.

**``path`` is a materialized ancestor path**, not a convenience column. Scope resolution
asks "is this department an ancestor-or-self of that one" on every permission check, and a
recursive CTE per request is the thing this avoids: the path is a ``/``-delimited string of
ancestor ids (leading and trailing slash), so descendant lookup is an indexed
``LIKE '/a/b/%'`` and ancestor-or-self is a prefix test. It is maintained on insert and
rewritten across a reparent, and nesting is capped (6 levels) in ``domain/`` — a department
tree that deep is already past what a cost-centre structure needs.
"""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class Department(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §3.12."""

    __tablename__ = "department"
    __table_args__ = (
        Index("ix_department_head_owner", "tenant_id", "head_user_id"),
        ForeignKeyConstraint(
            ["tenant_id", "head_user_id"],
            ["user.tenant_id", "user.id"],
            name="fk_department_head_owner",
        ),
        Index("ix_department_company_owner", "tenant_id", "company_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["company.tenant_id", "company.id"],
            name="fk_department_company_owner",
        ),
        Index("ix_department_parent_owner", "tenant_id", "company_id", "parent_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "parent_id"],
            ["department.tenant_id", "department.company_id", "department.id"],
            name="fk_department_parent_owner",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_department_owner_id"),
        # `code` is unique within its company, not its tenant: two companies may each
        # have a `SALES` department.
        UniqueConstraint("company_id", "code", name="uq_department_company_id_code"),
        # The materialized-path index for ancestor-or-self resolution. `tenant_id`
        # leads (§1.7): the session filter injects it into every query.
        Index("ix_department_tenant_id_path", "tenant_id", "path"),
        # Declared so InnoDB does not invent them, named after the constraint, and read
        # as autogenerate drift forever (§1.7 first exception — FK-supporting indexes).
        # `company_id` is served by `uq_department_company_id_code`, so no separate one.
        Index("ix_department_parent_id", "parent_id"),
        Index("ix_department_head_user_id", "head_user_id"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("company.id", name="fk_department_company_id"), nullable=False
    )
    #: Self-nesting. NULL is a top-level department. The FK proves the parent exists;
    #: that it is in the same company is a ``domain/`` check (a cross-company parent
    #: would corrupt the path and the scope tree).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, ForeignKey("department.id", name="fk_department_parent_id"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    cost_centre_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: The department head. A real relationship, so it carries a FK (§1.5), unlike the
    #: ``*_by`` metadata columns.
    head_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7, ForeignKey("user.id", name="fk_department_head_user_id"), nullable=True
    )
    #: ``/<ancestor-id-hex>/…/`` — see the module docstring. Maintained in ``domain/``.
    path: Mapped[str] = mapped_column(String(500), nullable=False)
