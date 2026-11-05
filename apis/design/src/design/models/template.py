"""SQLAlchemy models for the Invoice Designer (docs/invoice-design.md §4).

Six tables, all tenant-scoped through ``TenantMixin`` so the session-level filter
applies (CLAUDE.md §5.3). Table names are singular and ids are UUIDv7 ``BINARY(16)``
(CLAUDE.md §4).

**One lifecycle mechanism per entity** (rule 4.12). A template carries ``status``
(``StatusMixin``) and nothing else — retiring one is ``status = 'ARCHIVED'``, not a
second boolean. Assignments, assets and components carry ``is_active``
(``DeactivableMixin``) and no status. A version carries neither: it is immutable, and
"this is the live one" is a *date* — ``published_at`` — because a boolean cannot say
when a layout started printing.

**No compiled HTML or CSS is stored.** The renderer compiles from
``layout_definition``; accepting a precompiled document body would make every template
an injection vector into whatever renders it (docs/invoice-design.md §6.2).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import (
    AuditMixin,
    DeactivableMixin,
    IdMixin,
    StatusMixin,
    TenantMixin,
)
from billing_platform.db.types import UtcDateTime, Uuid7, utcnow
from sqlalchemy import (
    JSON,
    Boolean,
    Computed,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

#: Every amount and quantity column on the platform stores four decimals and is never
#: narrowed per column (CLAUDE.md §4). Page geometry follows the same storage scale: a
#: millimetre measurement is a quantity, and MySQL narrows a smaller scale silently.
MEASURE = Numeric(19, 4)

#: A template's lifecycle, as the only mechanism it has. ``ARCHIVED`` is this service's
#: soft delete: the row stays, because render snapshots point at it.
TEMPLATE_STATUSES: tuple[str, ...] = ("DRAFT", "PUBLISHED", "ARCHIVED")


class InvoiceTemplate(IdMixin, TenantMixin, StatusMixin, AuditMixin, Base):
    """A document design: page setup, status, and a pointer to the live version."""

    __tablename__ = "invoice_template"
    __table_args__ = (
        # Partial uniqueness, MySQL-style: ``live_code`` is NULL for an archived row and
        # MySQL permits many NULLs in a unique index, so one live code coexists with any
        # number of archived rows that once used it. A plain unique key on ``code`` burns
        # the code forever the first time a template is retired.
        UniqueConstraint(
            "tenant_id", "company_id", "live_code", name="uq_invoice_template_live_code"
        ),
        Index("ix_invoice_template_company", "tenant_id", "company_id"),
        Index("ix_invoice_template_lookup", "tenant_id", "company_id", "status", "created_at"),
        MARIADB_TABLE_ARGS,
    )

    #: ``SCOPE_ALL`` means tenant-wide: a shared house style every company inherits.
    #: Writing one requires tenant-scoped authority (``api/authorization.py``).
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False, default=SCOPE_ALL)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    live_code: Mapped[str | None] = mapped_column(
        String(50),
        Computed("CASE WHEN status <> 'ARCHIVED' THEN code ELSE NULL END", persisted=True),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paper_size: Mapped[str] = mapped_column(String(32), nullable=False, default="A4")
    page_orientation: Mapped[str] = mapped_column(String(16), nullable=False, default="PORTRAIT")
    page_width_mm: Mapped[Decimal | None] = mapped_column(MEASURE, nullable=True)
    page_height_mm: Mapped[Decimal | None] = mapped_column(MEASURE, nullable=True)
    unit_of_measure: Mapped[str] = mapped_column(String(8), nullable=False, default="mm")
    #: Shipped designs. A tenant may copy one; it may not edit, publish or archive it.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: What the design is for (designer plan P1, 2026-11-03): the voucher kind it prints and
    #: whether its lines are products, accounts or both. ``NULL`` is a template made before
    #: templates said, which any kind may still route to. Validated in the app, never an ENUM.
    voucher_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line_profile: Mapped[str | None] = mapped_column(String(16), nullable=True)

    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey(
            "invoice_template_version.id",
            ondelete="SET NULL",
            name="fk_invoice_template_current_version_id",
        ),
        nullable=True,
    )

    versions: Mapped[list[InvoiceTemplateVersion]] = relationship(
        "InvoiceTemplateVersion",
        back_populates="template",
        foreign_keys="[InvoiceTemplateVersion.template_id]",
        cascade="all, delete-orphan",
    )
    current_version: Mapped[InvoiceTemplateVersion | None] = relationship(
        "InvoiceTemplateVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )


class InvoiceTemplateVersion(IdMixin, TenantMixin, Base):
    """An immutable snapshot of the canvas layout tree.

    Never updated after insert except to stamp ``published_at``/``published_by``, which
    is what makes a reprint reproducible: a snapshot names the version it rendered, and
    that version's layout cannot have changed since (docs/invoice-design.md §7).
    """

    __tablename__ = "invoice_template_version"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "version_number", name="uq_invoice_template_version_number"
        ),
        Index("ix_invoice_template_version_template", "tenant_id", "template_id"),
        MARIADB_TABLE_ARGS,
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey(
            "invoice_template.id",
            ondelete="CASCADE",
            name="fk_invoice_template_version_template_id",
        ),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0.0")
    layout_definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: SHA-256 over the canonical layout JSON. Two versions that would render identically
    #: share a digest, and a snapshot can be checked against the layout it claims.
    layout_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Set once, when this version becomes the template's live layout. A date, not a
    #: boolean: "printing since when" is the question anyone asks of it (rule 4.12).
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)

    template: Mapped[InvoiceTemplate] = relationship(
        "InvoiceTemplate",
        back_populates="versions",
        foreign_keys=[template_id],
    )


class InvoiceTemplateAssignment(IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    """Which template a document of a given kind prints on.

    Resolution is priority, then specificity, and every criterion a rule sets must match
    (docs/invoice-design.md §5.2). A rule always names a template in its own company or a
    tenant-wide one — checked when the rule is written, not when it is read.
    """

    __tablename__ = "invoice_template_assignment"
    __table_args__ = (
        Index("ix_invoice_template_assignment_company", "tenant_id", "company_id"),
        Index(
            "ix_invoice_template_assignment_lookup",
            "tenant_id",
            "company_id",
            "voucher_kind",
            "is_active",
            "priority",
        ),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    voucher_type_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    customer_tax_category: Mapped[str | None] = mapped_column(String(32), nullable=True)

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey(
            "invoice_template.id",
            ondelete="CASCADE",
            name="fk_invoice_template_assignment_template_id",
        ),
        nullable=False,
    )
    #: Pins the rule to one version instead of following the template's live version.
    specific_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid7,
        ForeignKey(
            "invoice_template_version.id",
            ondelete="SET NULL",
            name="fk_invoice_template_assignment_version_id",
        ),
        nullable=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)


class InvoiceTemplateAsset(IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    """Brand graphics, signatures, seals and fonts a layout references.

    ``storage_path`` is derived by this service from its configured prefix, the tenant,
    the company and the asset id — never supplied by the client, which could otherwise
    name any object in the bucket (docs/invoice-design.md §6.3). There is no public-URL
    column: downloads are signed and expiring (CLAUDE.md §5.14).
    """

    __tablename__ = "invoice_template_asset"
    __table_args__ = (
        Index("ix_invoice_template_asset_company", "tenant_id", "company_id"),
        Index(
            "ix_invoice_template_asset_lookup",
            "tenant_id",
            "company_id",
            "is_active",
            "asset_type",
        ),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False, default=SCOPE_ALL)
    asset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="S3")
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    #: SHA-256 of the uploaded bytes as reported by the upload step. Lets a renderer
    #: detect a swapped object and a reviewer tie a printed logo to one file.
    content_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)


class InvoiceTemplateComponent(IdMixin, TenantMixin, DeactivableMixin, AuditMixin, Base):
    """Reusable blocks — bank instructions, terms, signatories — composed into layouts."""

    __tablename__ = "invoice_template_component"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "code", name="uq_invoice_template_component_code"
        ),
        Index("ix_invoice_template_component_company", "tenant_id", "company_id"),
        Index(
            "ix_invoice_template_component_lookup",
            "tenant_id",
            "company_id",
            "is_active",
            "component_category",
        ),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False, default=SCOPE_ALL)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    component_category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class InvoiceRenderSnapshot(IdMixin, TenantMixin, Base):
    """Print evidence: which template version produced which document artifact.

    Append-only. A reprint is a new row, never an update — "this invoice was printed
    twice" is a fact an auditor needs, and overwriting the first row would erase it.
    ``ON DELETE RESTRICT`` on both parents is CLAUDE.md invariant 12: a template version
    a document was printed from is never removable.
    """

    __tablename__ = "invoice_render_snapshot"
    __table_args__ = (
        Index("ix_invoice_render_snapshot_company", "tenant_id", "company_id"),
        Index("ix_invoice_render_snapshot_voucher", "tenant_id", "voucher_id", "rendered_at"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey(
            "invoice_template.id",
            ondelete="RESTRICT",
            name="fk_invoice_render_snapshot_template_id",
        ),
        nullable=False,
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7,
        ForeignKey(
            "invoice_template_version.id",
            ondelete="RESTRICT",
            name="fk_invoice_render_snapshot_version_id",
        ),
        nullable=False,
    )
    output_format: Mapped[str] = mapped_column(String(16), nullable=False, default="PDF")
    render_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    render_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rendered_by: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    rendered_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
