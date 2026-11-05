"""The largest Purchase bill prints within its budget, on every layout (designer plan §8 R5).

A bill carries at most 200 supply lines. Building its HTML is pure Python and must stay well
inside a second; the real browser renders a 200-line goods bill, on the standard layout and on a
designed two-table layout, within the render deadline with every line and the totals present.
The browser checks are selected with ``-k real_chromium`` (see ``test_print_sandbox_switch.py``).
"""

import io
import sys
import time
from pathlib import Path

import pytest
from billing_platform.ids import uuid7
from test_canvas_print import designed, element, zone
from test_purchase_print import snapshot

from vouchers.domain.purchase_print import render_html
from vouchers.tasks.print_child import DEFAULT_DEADLINE_SECONDS

LINES = 200
#: Coverage tracing (CI runs ``pytest --cov``) slows pure Python several times over; the budget
#: is for the code, not for the instrument measuring it.
TRACED = sys.gettrace() is not None or "coverage" in sys.modules
#: Generous for CI machines; the HTML for 200 lines builds well inside this untraced.
HTML_BUDGET_SECONDS = 5.0 if TRACED else 1.0
#: The child's own deadline is 60 s; a full bill must finish well before it, even on a busy
#: machine (about 6-7 s on an idle one, browser start included).
PDF_BUDGET_SECONDS = DEFAULT_DEADLINE_SECONDS * 0.75


def largest_bill(*, mixed: bool) -> dict:
    """200 lines: goods with quantity, unit, rate and HSN; every other one an expense if mixed."""
    value = snapshot()
    supply = value["document"]["invoice"]["supplies"][0]
    amount = value["calculation"]["lines"][0] | {
        "entered": "1250.0000",
        "commercial": "1250.0000",
        "taxable": "1250.0000",
        "payable": "1250.0000",
    }
    value["document"]["invoice"]["supplies"] = []
    value["calculation"]["lines"] = []
    value["labels"]["units"] = {}
    for index in range(LINES):
        key = str(uuid7())
        goods = not mixed or index % 2 == 0
        row = supply | {
            "line_key": key,
            "description": f"Item {index + 1:03d} " + "with a longer description " * 2,
            "supply_kind": "GOODS" if goods else "ACCOUNT",
            "hsn_sac": "0402" if goods else None,
        }
        if goods:
            row |= {"quantity": "12.5000", "rate": "100.0000"}
            value["labels"]["units"][key] = "kg"
        value["document"]["invoice"]["supplies"].append(row)
        value["calculation"]["lines"].append(amount | {"key": key})
    total = f"{1250 * LINES}.0000"
    value["calculation"] |= {"commercial_total": total, "payable": total}
    return value


def two_tables() -> dict:
    value_layout = designed()
    sections = value_layout["layout_definition"]["sections"]
    sections[1]["elements"][0]["columns"] = [
        {"key": key, "width_mm": width, "show": True}
        for key, width in (
            ("serial_no", 10),
            ("description", 70),
            ("hsn_sac", 20),
            ("quantity", 20),
            ("unit", 15),
            ("rate", 25),
            ("amount", 30),
        )
    ]
    sections.insert(
        2, zone("accounts", "CUSTOM", 10, 112, 190, 6, element("ACCOUNT_TABLE", 0, 0, 190, 6))
    )
    sections[3]["y"] = 125
    # A totals block prints inside its own box, so it is drawn tall enough for the words.
    sections[3]["elements"][0] |= {
        "totals_rows": ["subtotal", "grand_total", "amount_in_words"],
        "height": 30,
    }
    return value_layout


@pytest.mark.parametrize("mixed", [False, True], ids=["product", "mixed"])
@pytest.mark.parametrize("designed_layout", [False, True], ids=["standard", "designed"])
def test_the_largest_bill_builds_its_html_within_budget(mixed, designed_layout):
    value = largest_bill(mixed=mixed)
    if designed_layout:
        value["layout"] = two_tables()
    started = time.perf_counter()
    html = render_html(value)
    elapsed = time.perf_counter() - started
    assert elapsed < HTML_BUDGET_SECONDS, f"{elapsed:.3f}s for {LINES} lines"
    assert "Item 200" in html and "Rupees Two Lakh Fifty Thousand Only" in html


@pytest.mark.parametrize("designed_layout", [False, True], ids=["standard", "designed"])
async def test_real_chromium_the_largest_mixed_bill_prints_within_budget(designed_layout, tmp_path):
    from pypdf import PdfReader

    from vouchers.config import PrintRuntime
    from vouchers.tasks.print_child import render

    settings = PrintRuntime(database_url="sqlite+aiosqlite:///:memory:")
    executable = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    value = largest_bill(mixed=True)
    if designed_layout:
        value["layout"] = two_tables()
    started = time.perf_counter()
    data = await render(
        value,
        executable if executable.is_file() else None,
        sandbox=settings.print_chromium_sandbox,
    )
    elapsed = time.perf_counter() - started
    (tmp_path / "largest.pdf").write_bytes(data)
    assert elapsed < PDF_BUDGET_SECONDS, f"{elapsed:.1f}s for {LINES} lines"
    texts = [page.extract_text() for page in PdfReader(io.BytesIO(data)).pages]
    joined = " ".join(texts)
    assert len(texts) > 3
    assert "Item 001" in joined and "Item 200" in joined
    assert "Rupees Two Lakh Fifty Thousand Only" in joined
    assert "12.500 kg" in joined or "12.500" in joined
    # Every page names its bill, however far the table has run.
    assert all("Purchase voucher" in text and "BILL-123" in text for text in texts)
    if designed_layout:
        # The products table repeats its header on each page it continues onto.
        heading_pages = sum("HSN/SAC" in text for text in texts)
        assert heading_pages >= 2
