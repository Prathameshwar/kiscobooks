"""The drag-and-drop canvas definition (docs/invoice-design.md §6.2).

Every model here is ``extra="forbid"`` and every value is bounded. That is not
housekeeping: this tree is stored verbatim and later compiled into a document, so an
unvalidated key is an injection into whatever renders it. The rules this encodes:

* **No raw markup, no raw CSS.** Styling is typed scalars — a size in points, a colour
  as a hex triple, an alignment from a fixed set — and the renderer composes the
  stylesheet from them. A ``style`` string would let a layout carry
  ``expression(...)``, ``url(http://169.254.169.254/...)`` or ``</style><script>``
  straight into the output.
* **Bindings come from an allowlist of roots**, so an element cannot name an arbitrary
  server-side path. Field-level read denies are still applied by the renderer when it
  materializes values (CLAUDE.md §6.15); the allowlist bounds what may be *asked* for.
* **No open key/value bags.** There is no free-form ``props`` or ``metadata`` map. A
  dict with an arbitrary key set is ``extra="allow"`` under another name, and the keys a
  renderer treats as structural (``src``, ``style``, ``href``) are exactly the ones an
  attacker would choose. Element options will be typed per element type when the renderer
  defines them (docs/invoice-design.md §9).
* **Bounded everywhere.** Section and element counts are capped so one request cannot
  store a layout nothing can render.

Geometry inside this tree is display geometry in millimetres and points — ``float`` is
deliberate here, and only here. Money and quantities are ``Decimal`` columns
(CLAUDE.md §4, §6.1); a template's own page size is ``DECIMAL(19,4)`` on the row.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

#: What an element may bind to. Roots only — the renderer resolves the remainder against
#: the document it is printing, under that reader's field policy.
BINDING_ROOTS: tuple[str, ...] = (
    "voucher",
    "company",
    "party",
    "address",
    "line",
    "tax",
    "totals",
    "bank",
    "signatory",
    "custom",
)

#: Built from the roots above rather than restated: a second copy of this list is a copy
#: that eventually disagrees, and the regex is what actually enforces the allowlist.
_BINDING_PATTERN = rf"^({'|'.join(BINDING_ROOTS)})(\.[a-z][a-z0-9_]{{0,39}}){{1,3}}$"
_COLOUR_PATTERN = r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$"
#: Family names only — no ``url()``, no quotes, nothing a stylesheet could reinterpret.
_FONT_PATTERN = r"^[A-Za-z][A-Za-z0-9 \-]{0,63}(?:, ?[A-Za-z][A-Za-z0-9 \-]{0,63}){0,3}$"

Colour = Annotated[str, Field(pattern=_COLOUR_PATTERN, max_length=7)]
BindingPath = Annotated[str, Field(pattern=_BINDING_PATTERN, max_length=160)]


class CanvasMargins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top: float = Field(default=10.0, ge=0.0, le=100.0)
    bottom: float = Field(default=10.0, ge=0.0, le=100.0)
    left: float = Field(default=10.0, ge=0.0, le=100.0)
    right: float = Field(default=10.0, ge=0.0, le=100.0)
    unit: Literal["mm", "in", "pt", "px"] = "mm"


class CanvasPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: Literal["A4", "LETTER", "A5", "THERMAL_80MM", "THERMAL_58MM", "CUSTOM"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margins: CanvasMargins = Field(default_factory=CanvasMargins)
    grid_snap: bool = True
    grid_size: float = Field(default=5.0, ge=1.0, le=50.0)


class CanvasTheme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_color: Colour = "#1E40AF"
    secondary_color: Colour | None = None
    font_family: str = Field(default="Inter, sans-serif", pattern=_FONT_PATTERN, max_length=128)
    font_size_pt: float = Field(default=9.0, ge=4.0, le=72.0)


class CanvasStyle(BaseModel):
    """Typed styling. The renderer composes CSS from these; none of it is CSS itself."""

    model_config = ConfigDict(extra="forbid")

    font_size_pt: float | None = Field(default=None, ge=4.0, le=72.0)
    font_weight: Literal["normal", "medium", "semibold", "bold"] | None = None
    font_style: Literal["normal", "italic"] | None = None
    color: Colour | None = None
    background_color: Colour | None = None
    text_align: Literal["left", "center", "right", "justify"] | None = None
    vertical_align: Literal["top", "middle", "bottom"] | None = None
    border_width_mm: float | None = Field(default=None, ge=0.0, le=10.0)
    border_style: Literal["none", "solid", "dashed", "dotted"] | None = None
    border_color: Colour | None = None
    padding_mm: float | None = Field(default=None, ge=0.0, le=50.0)
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    line_height: float | None = Field(default=None, ge=0.5, le=4.0)
    uppercase: bool | None = None


class CanvasElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal[
        "TEXT",
        "FIELD_BINDING",
        "IMAGE",
        "ITEM_TABLE",
        "TAX_SUMMARY",
        "QR_CODE",
        "BARCODE",
        "SHAPE",
        "DIVIDER",
        "SIGNATURE",
    ]
    x: float = Field(ge=-1000.0, le=2000.0)
    y: float = Field(ge=-1000.0, le=2000.0)
    width: float = Field(gt=0.0, le=2000.0)
    height: float = Field(gt=0.0, le=2000.0)
    z_index: int = Field(default=1, ge=0, le=1000)
    #: Static text the renderer prints as text, never as markup.
    content: str | None = Field(default=None, max_length=2000)
    binding_path: BindingPath | None = None
    label: str | None = Field(default=None, max_length=200)
    #: Names an ``invoice_template_asset`` for ``IMAGE`` and ``SIGNATURE`` elements. The
    #: service checks the asset belongs to this company before a version is stored.
    asset_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    )
    style: CanvasStyle = Field(default_factory=CanvasStyle)
    #: Typed options for the types that need them. ``QR_CODE``/``BARCODE`` carry a
    #: symbology and whether the human-readable value prints; ``IMAGE`` carries a fit.
    #: Anything else a renderer needs becomes another typed field here, never a free map.
    symbology: Literal["CODE128", "EAN13", "QR", "DATAMATRIX"] | None = None
    show_value: bool | None = None
    image_fit: Literal["contain", "cover", "fill"] | None = None


class CanvasSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal[
        "HEADER", "BILLING_SHIPPING", "ITEM_TABLE", "TAX_SUMMARY", "TOTALS", "FOOTER", "CUSTOM"
    ]
    title: str | None = Field(default=None, max_length=200)
    height: float | None = Field(default=None, gt=0.0, le=2000.0)
    #: Names an ``invoice_template_component`` whose content this section renders.
    component_code: str | None = Field(default=None, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    elements: list[CanvasElement] = Field(default_factory=list, max_length=200)


class CanvasV10(BaseModel):
    """The ``1.0.0`` root layout tree — **frozen**.

    Not kept for politeness. A version row stores this tree verbatim and a
    ``layout_digest`` over those exact bytes (docs/invoice-design.md §4.3), so a reprint of a
    published document verifies against them. Widening this model would make every stored
    1.0.0 layout re-validate against a different shape, and *normalising* one on read would
    change its digest and silently invalidate the evidence. New capability goes in a new
    schema version beside this one; nothing here moves again.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    page: CanvasPage = Field(default_factory=CanvasPage)
    theme: CanvasTheme = Field(default_factory=CanvasTheme)
    sections: list[CanvasSection] = Field(default_factory=list, max_length=40)


# =============================================================================
# 1.1.0 — item-table columns, totals rows, tax grouping and print options
# =============================================================================
#
# Ratified 2026-10-27, closing open question §9.3. The vocabulary is the one the designer
# front end was driven against until it printed four real documents (a GST tax invoice, a
# compact A4, an 80mm roll and a delivery challan), which is why it is typed fields rather
# than the free map a renderer-first design would have been tempted into.

#: What a printed copy is marked as. India's GST rules name the first three; the fourth is
#: for anyone who wants a file copy.
CopyLabel = Literal[
    "ORIGINAL_FOR_RECIPIENT",
    "DUPLICATE_FOR_TRANSPORTER",
    "TRIPLICATE_FOR_SUPPLIER",
    "EXTRA_COPY",
]

#: The columns an item table may carry. A closed vocabulary, because each one is a value the
#: renderer has to *resolve* — an open string here would be a binding path by another name.
ColumnKey = Literal[
    "serial_no",
    "description",
    "hsn_sac",
    "batch",
    "expiry",
    "quantity",
    "unit",
    "rate",
    "mrp",
    "discount",
    "taxable_value",
    "cgst_rate",
    "cgst_amount",
    "sgst_rate",
    "sgst_amount",
    "igst_rate",
    "igst_amount",
    "cess",
    "amount",
    #: The ledger a line posts to — the first column of an accounts table (plan D2, 2026-11-03).
    "account",
]

#: The rows a totals block may print. ``amount_in_words`` and ``outstanding_balance`` are
#: here because a GST invoice routinely carries both.
TotalsRow = Literal[
    "subtotal",
    "discount",
    "taxable_value",
    "cgst",
    "sgst",
    "igst",
    "cess",
    "round_off",
    "grand_total",
    "amount_in_words",
    "outstanding_balance",
]


def _one_original() -> list[CopyLabel]:
    """A named factory, so the default's element type is the literal and not ``str``."""
    return ["ORIGINAL_FOR_RECIPIENT"]


class PrintOptions(BaseModel):
    """How many copies print, and what each is marked as."""

    model_config = ConfigDict(extra="forbid")

    copies: list[CopyLabel] = Field(default_factory=_one_original, max_length=4)
    copy_mark_position: Literal["top-right", "top-center", "watermark"] | None = None
    #: The letterhead is already on the stock, so the renderer leaves the header area blank.
    pre_printed_stationery: bool = False

    @model_validator(mode="after")
    def copies_are_distinct_and_present(self) -> PrintOptions:
        if not self.copies:
            raise ValueError("at least one printed copy is required")
        if len(set(self.copies)) != len(self.copies):
            raise ValueError("each printed copy may be marked only once")
        return self


class ItemColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: ColumnKey
    #: Overrides the default heading. The default comes from the renderer's catalogue, so a
    #: template that wants "Particulars" instead of "Description" says so and nothing else does.
    label: str | None = Field(default=None, max_length=60)
    width_mm: float = Field(gt=0.0, le=500.0)
    align: Literal["left", "center", "right"] | None = None
    show: bool = True


class RowOptions(BaseModel):
    """How the body rows of an item table are drawn."""

    model_config = ConfigDict(extra="forbid")

    description_under_item: bool | None = None
    zebra: bool | None = None
    repeat_header: bool | None = None
    #: Filler rows for pre-printed stationery, so a ruled box always looks full.
    blank_rows: int | None = Field(default=None, ge=0, le=50)


class CanvasPageV11(BaseModel):
    """Page *setup* — margins and the editor's grid.

    **Paper size and orientation are deliberately absent.** They live on the template row
    (``paper_size``, ``page_orientation``, ``page_width_mm``, ``page_height_mm``), which is
    where they are ``DECIMAL(19,4)`` and where ``CUSTOM`` is validated to carry both
    dimensions. 1.0.0 restated size and orientation inside the tree as well — in the opposite
    case — which gave one document two answers to "what paper is this?" and nothing to
    resolve them with. One source of truth; see the decision log.
    """

    model_config = ConfigDict(extra="forbid")

    margins: CanvasMargins = Field(default_factory=CanvasMargins)
    grid_snap: bool = True
    #: Named for its unit, like everything else inside the tree. 1.0.0's ``grid_size`` did not
    #: say what it was measured in, and the editor had already decided it was millimetres.
    grid_step_mm: float = Field(default=5.0, ge=0.5, le=50.0)


class CanvasElementV11(CanvasElement):
    """1.0.0's element, plus the typed options the item table and totals block need."""

    type: Literal[  # type: ignore[assignment]  # widened by one value; see TOTALS_BLOCK below
        "TEXT",
        "FIELD_BINDING",
        "IMAGE",
        "ITEM_TABLE",
        #: Accounts and expenses on a bill, beside or instead of the products (plan D2,
        #: 2026-11-03). Widening the vocabulary leaves every stored 1.1.0 layout valid and its
        #: digest untouched, which is why it joins 1.1.0 rather than opening a new version.
        "ACCOUNT_TABLE",
        "TAX_SUMMARY",
        #: 1.0.0 had no way to say "print the totals here" except as free text, so every
        #: template that needed one hand-placed its rows and lost them on the next edit.
        "TOTALS_BLOCK",
        "QR_CODE",
        "BARCODE",
        "SHAPE",
        "DIVIDER",
        "SIGNATURE",
    ]
    columns: list[ItemColumn] | None = Field(default=None, max_length=24)
    row_options: RowOptions | None = None
    totals_rows: list[TotalsRow] | None = Field(default=None, max_length=11)
    tax_grouping: Literal["by_rate", "by_hsn", "none"] | None = None
    show_cess: bool | None = None

    @model_validator(mode="after")
    def options_belong_to_their_element_type(self) -> CanvasElementV11:
        """An option is refused on a type that cannot act on it.

        Accepting ``totals_rows`` on a ``DIVIDER`` would store a layout whose meaning depends
        on which fields the renderer happens to look at — the same class of problem as an open
        map, arrived at by a different route.
        """
        for field, allowed in (
            ("columns", {"ITEM_TABLE", "ACCOUNT_TABLE"}),
            ("row_options", {"ITEM_TABLE", "ACCOUNT_TABLE"}),
            ("totals_rows", {"TOTALS_BLOCK"}),
            ("tax_grouping", {"TAX_SUMMARY"}),
            ("show_cess", {"TAX_SUMMARY"}),
        ):
            if getattr(self, field) is not None and self.type not in allowed:
                raise ValueError(f"{field} is not an option of a {self.type} element")
        if self.columns is not None:
            keys = [column.key for column in self.columns]
            if len(set(keys)) != len(keys):
                raise ValueError("an item table may carry each column only once")
            if not any(column.show for column in self.columns):
                raise ValueError("an item table needs at least one visible column")
            # The error the designer front end found by printing a real invoice: a column set
            # summing to 204mm inside a 190mm table, which no renderer can honour and which
            # only shows up as a clipped last column on paper.
            shown = sum(column.width_mm for column in self.columns if column.show)
            if shown > self.width + 0.05:
                raise ValueError(
                    f"visible columns total {shown:g}mm, wider than the {self.width:g}mm table"
                )
        if self.totals_rows is not None:
            if not self.totals_rows:
                raise ValueError("a totals block needs at least one row")
            if len(set(self.totals_rows)) != len(self.totals_rows):
                raise ValueError("a totals block may print each row only once")
        return self


class CanvasSectionV11(CanvasSection):
    """1.0.0's section, with the millimetre box the editor outlines and selects."""

    #: 1.0.0 carried an optional ``height`` and nothing else, so a zone had no position and
    #: the editor could not hit-test one. All four are required here.
    x: float = Field(ge=-1000.0, le=2000.0)
    y: float = Field(ge=-1000.0, le=2000.0)
    width: float = Field(gt=0.0, le=2000.0)
    height: float = Field(gt=0.0, le=2000.0)
    #: Off, the zone lays its elements out itself. On, they keep their own coordinates and may
    #: be dragged anywhere on the page.
    free_placement: bool = False
    elements: list[CanvasElementV11] = Field(default_factory=list, max_length=200)  # type: ignore[assignment]  # 1.1.0 elements


class CanvasV11(BaseModel):
    """The ``1.1.0`` root layout tree."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1.0"] = "1.1.0"
    page: CanvasPageV11 = Field(default_factory=CanvasPageV11)
    theme: CanvasTheme = Field(default_factory=CanvasTheme)
    print_options: PrintOptions = Field(default_factory=PrintOptions)
    sections: list[CanvasSectionV11] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> CanvasV11:
        """One id per section and per element, across the whole tree.

        The editor addresses selection, undo and z-order by id, and a renderer resolving a
        duplicate would pick whichever it saw last. 1.0.0 never checked this.
        """
        section_ids = [section.id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("section identifiers must be unique within a layout")
        element_ids = [element.id for section in self.sections for element in section.elements]
        if len(set(element_ids)) != len(element_ids):
            raise ValueError("element identifiers must be unique within a layout")
        return self


#: The stored tree, at whichever version it was written. Discriminated on ``schema_version``,
#: so a request names its own contract and a stored row re-validates against the shape it was
#: written against — never against a newer one.
CanvasDefinition = Annotated[CanvasV10 | CanvasV11, Field(discriminator="schema_version")]

#: Use this to parse one. A discriminated-union alias is a type, not a class, so it carries no
#: ``model_validate`` of its own.
CANVAS: TypeAdapter[CanvasV10 | CanvasV11] = TypeAdapter(CanvasDefinition)
