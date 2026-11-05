"""Canvas ``1.1.0`` — the options the editor needs, and the rules that make them safe.

Beside `test_canvas_validation.py` rather than inside it: that module is the 1.0.0 injection
suite and 1.0.0 is frozen, so mixing the two would make it unclear which contract a failing
assertion is about. Every defence there applies here too, and the last test proves it.

The vocabulary under test is the one the designer front end was driven against until it
printed four real documents. Two of the rules below exist *because* of that: a column set
summing wider than its table, and a zone with no box to hit-test.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from design.schemas.canvas import CANVAS, CanvasV10, CanvasV11

pytestmark = pytest.mark.asyncio


def zone(**overrides: object) -> dict[str, object]:
    return {
        "id": "sec_body",
        "type": "ITEM_TABLE",
        "x": 10.0,
        "y": 10.0,
        "width": 190.0,
        "height": 100.0,
        **overrides,
    }


def table(**overrides: object) -> dict[str, object]:
    return {
        "id": "el_items",
        "type": "ITEM_TABLE",
        "x": 0.0,
        "y": 0.0,
        "width": 190.0,
        "height": 60.0,
        **overrides,
    }


def v11(element: dict[str, object]) -> dict[str, object]:
    """A 1.1.0 layout with one zone holding one element."""
    return {"schema_version": "1.1.0", "sections": [zone(elements=[element])]}


async def test_version_selects_the_contract_a_tree_was_written_against() -> None:
    """This is what keeps ``layout_digest`` meaningful.

    A stored 1.0.0 row is parsed by the frozen 1.0.0 model, so no stored byte is
    reinterpreted — and nothing normalises one on read, which would change its digest and
    invalidate a published document's print evidence (docs/invoice-design.md §4.3).
    """
    stored = {"schema_version": "1.0.0", "sections": [{"id": "a", "type": "HEADER"}]}
    assert isinstance(CANVAS.validate_python(stored), CanvasV10)
    assert isinstance(CANVAS.validate_python({"schema_version": "1.1.0"}), CanvasV11)
    # An unknown or absent version is refused outright rather than guessed at.
    for bad in ({"schema_version": "1.2.0"}, {"sections": []}):
        with pytest.raises(ValidationError):
            CANVAS.validate_python(bad)


async def test_v10_cannot_express_v11_capability() -> None:
    """1.0.0 is frozen, so the new options must not reach it through inheritance."""
    for extra in (
        {"print_options": {"copies": ["ORIGINAL_FOR_RECIPIENT"]}},
        {"sections": [{"id": "a", "type": "ITEM_TABLE", "free_placement": True}]},
        {"sections": [{"id": "a", "type": "ITEM_TABLE", "x": 1.0, "y": 1.0, "width": 10.0}]},
    ):
        with pytest.raises(ValidationError):
            CanvasV10.model_validate({"schema_version": "1.0.0", **extra})


async def test_item_table_columns_round_trip() -> None:
    layout = CANVAS.validate_python(
        v11(
            table(
                columns=[
                    {"key": "description", "width_mm": 120.0, "show": True},
                    {"key": "quantity", "width_mm": 30.0, "align": "right", "show": True},
                    {"key": "amount", "width_mm": 40.0, "align": "right", "show": True},
                ],
                row_options={"zebra": True, "repeat_header": True, "blank_rows": 3},
            )
        )
    )
    assert isinstance(layout, CanvasV11)
    element = layout.sections[0].elements[0]
    assert element.columns is not None
    assert [column.key for column in element.columns] == ["description", "quantity", "amount"]
    assert element.row_options is not None
    assert element.row_options.blank_rows == 3
    assert layout.sections[0].free_placement is False


async def test_columns_wider_than_their_table_are_refused() -> None:
    """The error a real printed invoice found: 204mm of columns in a 190mm table.

    No renderer can honour it, and on paper it shows up as a clipped last column — the worst
    place to discover it. 1.0.0 could not express columns at all, so the rule arrives with
    them rather than after them.
    """
    with pytest.raises(ValidationError, match="wider than"):
        CANVAS.validate_python(
            v11(
                table(
                    columns=[
                        {"key": "description", "width_mm": 164.0, "show": True},
                        {"key": "amount", "width_mm": 40.0, "show": True},
                    ]
                )
            )
        )


async def test_a_hidden_column_does_not_count_against_the_width() -> None:
    """Hiding a column is how a template is narrowed, so its width must stop counting."""
    layout = CANVAS.validate_python(
        v11(
            table(
                columns=[
                    {"key": "description", "width_mm": 164.0, "show": True},
                    {"key": "mrp", "width_mm": 40.0, "show": False},
                ]
            )
        )
    )
    assert isinstance(layout, CanvasV11)


async def test_a_column_set_may_exactly_fill_its_table() -> None:
    """The common case, and the one a strict inequality would have broken."""
    layout = CANVAS.validate_python(
        v11(
            table(
                width=190.0,
                columns=[
                    {"key": "description", "width_mm": 150.0, "show": True},
                    {"key": "amount", "width_mm": 40.0, "show": True},
                ],
            )
        )
    )
    assert isinstance(layout, CanvasV11)


@pytest.mark.parametrize(
    ("columns", "message"),
    [
        ([{"key": "amount", "width_mm": 20.0, "show": True}] * 2, "only once"),
        ([{"key": "amount", "width_mm": 20.0, "show": False}], "at least one visible"),
        ([], "at least one visible"),
    ],
)
async def test_column_sets_that_mean_nothing_are_refused(
    columns: list[dict[str, object]], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        CANVAS.validate_python(v11(table(columns=columns)))


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("columns", [{"key": "amount", "width_mm": 10.0, "show": True}]),
        ("row_options", {"zebra": True}),
        ("totals_rows", ["grand_total"]),
        ("tax_grouping", "by_rate"),
        ("show_cess", True),
    ],
)
async def test_an_option_is_refused_on_a_type_that_cannot_act_on_it(
    option: str, value: object
) -> None:
    """The same class of problem as an open map, reached by a different route.

    A ``DIVIDER`` carrying ``totals_rows`` stores a layout whose meaning depends on which
    fields the renderer happens to read.
    """
    with pytest.raises(ValidationError, match="not an option"):
        CANVAS.validate_python(v11(table(type="DIVIDER", **{option: value})))


async def test_totals_block_is_a_first_class_element() -> None:
    """1.0.0 had no way to say "print the totals here" except as free text."""
    layout = CANVAS.validate_python(
        v11(
            table(
                type="TOTALS_BLOCK",
                totals_rows=["subtotal", "cgst", "sgst", "round_off", "grand_total"],
            )
        )
    )
    assert isinstance(layout, CanvasV11)
    assert layout.sections[0].elements[0].totals_rows == [
        "subtotal",
        "cgst",
        "sgst",
        "round_off",
        "grand_total",
    ]


@pytest.mark.parametrize(
    ("rows", "message"), [([], "at least one row"), (["cgst", "cgst"], "only once")]
)
async def test_totals_rows_that_mean_nothing_are_refused(rows: list[str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CANVAS.validate_python(v11(table(type="TOTALS_BLOCK", totals_rows=rows)))


async def test_tax_summary_carries_its_own_grouping() -> None:
    layout = CANVAS.validate_python(
        v11(table(type="TAX_SUMMARY", tax_grouping="by_hsn", show_cess=False))
    )
    assert isinstance(layout, CanvasV11)
    assert layout.sections[0].elements[0].tax_grouping == "by_hsn"


async def test_print_options_default_to_one_marked_original() -> None:
    layout = CANVAS.validate_python({"schema_version": "1.1.0"})
    assert isinstance(layout, CanvasV11)
    assert layout.print_options.copies == ["ORIGINAL_FOR_RECIPIENT"]
    assert layout.print_options.pre_printed_stationery is False
    assert layout.print_options.copy_mark_position is None


@pytest.mark.parametrize(
    ("copies", "message"),
    [
        ([], "at least one printed copy"),
        (["ORIGINAL_FOR_RECIPIENT", "ORIGINAL_FOR_RECIPIENT"], "only once"),
    ],
)
async def test_copy_sets_that_mean_nothing_are_refused(copies: list[str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CANVAS.validate_python({"schema_version": "1.1.0", "print_options": {"copies": copies}})


async def test_page_setup_no_longer_restates_the_paper() -> None:
    """One source of truth for what paper this is: the template row.

    1.0.0 carried ``size`` and ``orientation`` inside the tree *as well*, in the opposite case
    to the row's, with nothing to resolve a disagreement. See the decision log.
    """
    for restated in ({"size": "A4"}, {"orientation": "portrait"}, {"grid_size": 5.0}):
        with pytest.raises(ValidationError):
            CANVAS.validate_python({"schema_version": "1.1.0", "page": restated})
    layout = CANVAS.validate_python(
        {"schema_version": "1.1.0", "page": {"grid_snap": False, "grid_step_mm": 2.5}}
    )
    assert isinstance(layout, CanvasV11)
    assert layout.page.grid_step_mm == 2.5


async def test_duplicate_identifiers_are_refused() -> None:
    """The editor addresses selection, undo and z-order by id; a renderer takes the last."""
    with pytest.raises(ValidationError, match="element identifiers"):
        CANVAS.validate_python(
            {
                "schema_version": "1.1.0",
                "sections": [zone(elements=[table(id="dup"), table(id="dup", y=70.0)])],
            }
        )
    with pytest.raises(ValidationError, match="section identifiers"):
        CANVAS.validate_python(
            {
                "schema_version": "1.1.0",
                "sections": [zone(id="same"), zone(id="same", type="FOOTER", y=120.0)],
            }
        )


async def test_a_zone_needs_a_box_it_can_be_hit_tested_in() -> None:
    """1.0.0's section had an optional height and no position, so it had no geometry."""
    for incomplete in (
        {"id": "a", "type": "HEADER"},
        {"id": "a", "type": "HEADER", "x": 1.0, "y": 1.0},
        {"id": "a", "type": "HEADER", "x": 1.0, "y": 1.0, "width": 10.0},
        {"id": "a", "type": "HEADER", "x": 1.0, "y": 1.0, "width": 0.0, "height": 10.0},
    ):
        with pytest.raises(ValidationError):
            CANVAS.validate_python({"schema_version": "1.1.0", "sections": [incomplete]})


async def test_v11_keeps_every_1_0_0_defence() -> None:
    """The injection rules are the point of the sibling module; 1.1.0 inherits all of them."""
    for hostile in (
        table(style={"color": "red"}),
        table(style={"border": "1px solid red"}),
        table(binding_path="voucher.../../etc/passwd"),
        table(binding_path="secrets.api_key"),
        table(props={"src": "http://169.254.169.254/"}),
        table(content="x" * 2001),
        table(width=0.0),
    ):
        with pytest.raises(ValidationError):
            CANVAS.validate_python(v11(hostile))
    # And the theme is still family names only, never anything a stylesheet reinterprets.
    with pytest.raises(ValidationError):
        CANVAS.validate_python(
            {"schema_version": "1.1.0", "theme": {"font_family": "url(http://evil.test/f.woff)"}}
        )
