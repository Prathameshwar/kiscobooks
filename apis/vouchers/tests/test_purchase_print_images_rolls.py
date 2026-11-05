"""Pictures, rolls and layout previews on a Purchase print (designer plan §8 R2-R4, 2026-11-04).

A picture prints only from the bytes Design resolved, re-checked here; a roll is one page as
long as its content; a preview of a saved design version says so on every page and needs the
person's design read permission at creation and again at delivery.
"""

import base64
import copy
import hashlib
import io
import struct
import uuid
import zlib
from pathlib import Path

import pytest
from billing_platform.errors import ValidationFailedError
from conftest import headers
from test_canvas_print import designed, element, printed
from test_purchase_goods_capture import goods_bill
from test_purchase_goods_print import configure, displayed, facts_for
from test_purchase_print import snapshot
from voucher_execution.transport import ExecutionClient

from vouchers.domain.print_capabilities import PURCHASE, problems
from vouchers.domain.purchase_print import page_templates, render_html
from vouchers.tasks import purchase_print
from vouchers.tasks.print_child import ROLL_MAX_MM, roll_length

ASSET = "0199a1eb-0000-7000-8000-0000000000aa"


def png(width: int = 8, height: int = 4) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    body = zlib.compress((b"\x00" + bytes((200, 30, 30)) * width) * height)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b"")
    )


LOGO = png()


def resolved(data: bytes = LOGO, **changes: object) -> dict:
    return {
        "asset_id": ASSET,
        "status": "READY",
        "mime_type": "image/png",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_base64": base64.b64encode(data).decode(),
    } | changes


def with_logo(**asset: object) -> dict:
    value_layout = designed()
    value_layout["layout_definition"]["sections"][0]["elements"].append(
        element("IMAGE", 90, 0, 25, 12, asset_id=ASSET, image_fit="cover", label="Our logo")
    )
    value_layout["assets"] = [resolved(**asset)]
    return value_layout


# --- pictures ---


def test_a_resolved_picture_is_embedded_as_checked_data_and_nothing_else():
    html = printed(with_logo())
    expected = "data:image/png;base64," + base64.b64encode(LOGO).decode()
    assert f'src="{expected}"' in html
    assert 'class="canvas-img canvas-img--cover"' in html and 'alt="Our logo"' in html
    assert "img-src data:" in html
    assert "http" not in html.split("<main>")[1]


def test_the_standard_layout_still_embeds_no_pictures():
    assert "img-src 'none'" in render_html(snapshot())


def test_a_signature_prints_its_picture_above_the_line():
    value_layout = designed()
    signature = value_layout["layout_definition"]["sections"][2]["elements"][1]
    signature["asset_id"] = ASSET
    value_layout["assets"] = [resolved()]
    html = printed(value_layout)
    sign = html.split('class="canvas-el canvas-sign"')[1].split("</div>")[0]
    assert sign.index("<img") < sign.index("canvas-sign-line")


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "0" * 64},
        {"size_bytes": len(LOGO) + 1},
        {"mime_type": "image/jpeg"},
        {"mime_type": "image/svg+xml"},
        {"content_base64": "not base64!"},
    ],
    ids=["digest", "size", "type-mismatch", "svg", "base64"],
)
def test_a_picture_that_does_not_prove_what_it_claims_is_refused(change):
    with pytest.raises(ValidationFailedError, match="picture"):
        printed(with_logo(**change))


def test_pictures_over_their_combined_bound_are_refused():
    big = b"\x89PNG\r\n\x1a\n" + bytes(PURCHASE["images"]["max_bytes"] - 8)
    value_layout = with_logo(data=big)
    value_layout["assets"] = [resolved(big), resolved(big, asset_id=str(uuid.uuid4()))]
    with pytest.raises(ValidationFailedError, match="combined bound"):
        printed(value_layout)


@pytest.mark.parametrize(
    ("status", "words"),
    [
        ("WITHDRAWN", "has been withdrawn"),
        ("TOO_LARGE", "larger than 512 KB"),
        ("OVER_BUDGET", "640 KB together"),
        ("MISSING", "no longer available"),
    ],
)
def test_a_picture_design_could_not_send_is_refused_with_its_reason(status, words):
    value_layout = with_logo()
    value_layout["assets"] = [{"asset_id": ASSET, "status": status}]
    with pytest.raises(ValidationFailedError, match=words):
        printed(value_layout)
    unresolved = with_logo()
    unresolved["assets"] = []
    assert any("no longer available" in reason for _, reason in problems(unresolved, PURCHASE))


def test_the_designer_judges_only_shape_where_no_pictures_were_resolved():
    stored = with_logo()
    del stored["assets"]
    assert problems(stored, PURCHASE) == []
    empty = designed()
    empty["layout_definition"]["sections"][0]["elements"].append(element("IMAGE", 0, 0, 5, 5))
    assert ("el-image-0-0", "an image on this layout has no picture chosen") in problems(
        empty, PURCHASE
    )


# --- rolls ---


def roll(size: str = "THERMAL_80MM") -> dict:
    value_layout = designed()
    value_layout["paper_size"] = size
    for section in value_layout["layout_definition"]["sections"]:
        section["x"], section["width"] = 2, 76 if size == "THERMAL_80MM" else 54
        for row in section["elements"]:
            row["x"], row["width"] = 0, min(row["width"], 50)
    return value_layout


@pytest.mark.parametrize(("size", "width"), [("THERMAL_80MM", "80mm"), ("THERMAL_58MM", "58mm")])
def test_a_roll_is_one_page_at_its_width_naming_its_bill_at_the_end(size, width):
    html = printed(roll(size))
    assert f"@page {{ size: {width} 5000mm; margin: 0; }}" in html
    assert f"main {{ width: {width};" in html
    assert 'class="roll-identity"' in html and "Purchase voucher · DRAFT" in html
    assert problems(roll(size), PURCHASE) == []


def test_a_roll_length_is_whole_millimetres_within_the_ceiling():
    assert roll_length(96 / 25.4 * 100) == 101
    with pytest.raises(ValueError):
        roll_length(96 / 25.4 * (ROLL_MAX_MM + 5))


# --- previews ---


def preview_layout() -> dict:
    value_layout = designed()
    value_layout |= {
        "preview": True,
        "template_id": str(uuid.uuid4()),
        "version_id": str(uuid.uuid4()),
    }
    return value_layout


def test_a_preview_says_so_on_every_copy_and_every_page():
    value_layout = preview_layout()
    value_layout["layout_definition"]["print_options"]["copies"] = [
        "ORIGINAL_FOR_RECIPIENT",
        "TRIPLICATE_FOR_SUPPLIER",
    ]
    html = printed(value_layout)
    assert html.count("Layout preview · not for use") == 2
    value = snapshot()
    value["layout"] = value_layout
    assert "Layout preview · Purchase voucher" in page_templates(value)[1]


def test_a_preview_must_name_one_saved_designed_version():
    value_layout = preview_layout()
    del value_layout["version_id"]
    with pytest.raises(ValidationFailedError, match="layout preview"):
        printed(value_layout)


async def preview_request(client, prefix, app, tmp_path, monkeypatch, permissions, resolved_as):
    created, _ = await goods_bill(client, prefix, app)
    saved = created.json()
    configure(app, tmp_path)
    asked = []

    async def owner(self, command):
        return facts_for(command.preview.invoice)

    async def layout(owner, tenant, company, type_id, currency, preview=None):
        asked.append(preview)
        return resolved_as(preview)

    monkeypatch.setattr(ExecutionClient, "purchase_print", owner)
    monkeypatch.setattr(purchase_print, "resolve", layout)
    target = {"template_id": str(uuid.uuid4()), "version_id": str(uuid.uuid4())}
    auth = displayed()
    if permissions is not None:
        granted = headers(permissions=permissions, features=frozenset({"inventory"}))
        auth["X-Actor-Context"] = granted["X-Actor-Context"]
        auth["X-Actor-Signature"] = granted["X-Actor-Signature"]
    result = await client.post(
        prefix + "/vouchers/" + saved["id"] + "/print-jobs",
        headers=auth,
        json={
            "expected_version": saved["row_version"],
            "revision_id": saved["revision_id"],
            "layout_preview": target,
        },
    )
    return result, asked, target


def as_preview(preview):
    value_layout = designed()
    return value_layout | {
        "preview": True,
        "template_id": str(preview.template_id),
        "version_id": str(preview.version_id),
        "assets": [],
    }


async def test_a_preview_needs_design_read_permission_before_any_owner_is_asked(
    client, prefix, app, tmp_path, monkeypatch
):
    from conftest import PERMISSIONS

    result, asked, _ = await preview_request(
        client, prefix, app, tmp_path, monkeypatch, PERMISSIONS, as_preview
    )
    assert result.status_code == 403
    assert asked == []


async def test_a_preview_prints_the_asked_version_marked_as_a_preview(
    client, prefix, app, tmp_path, monkeypatch
):
    from billing_platform.db import tenant_scope
    from conftest import PERMISSIONS, TENANT
    from sqlalchemy import select

    from vouchers.models.printing import VoucherPrintJob

    granted = PERMISSIONS | {"design.template.read"}
    result, asked, target = await preview_request(
        client, prefix, app, tmp_path, monkeypatch, granted, as_preview
    )
    assert result.status_code == 202, result.text
    assert [str(row.version_id) for row in asked] == [target["version_id"]]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.scalar(select(VoucherPrintJob))
    assert job.snapshot["layout"]["preview"] is True
    assert "Layout preview · not for use" in render_html(job.snapshot)


async def test_a_preview_resolved_to_another_version_is_refused(
    client, prefix, app, tmp_path, monkeypatch
):
    from conftest import PERMISSIONS

    def elsewhere(preview):
        return as_preview(preview) | {"version_id": str(uuid.uuid4())}

    result, *_ = await preview_request(
        client,
        prefix,
        app,
        tmp_path,
        monkeypatch,
        PERMISSIONS | {"design.template.read"},
        elsewhere,
    )
    assert result.status_code == 409


async def test_delivering_a_preview_rechecks_design_read_permission(monkeypatch):
    from vouchers.schemas.printing import PrintCreate

    value = snapshot()
    value["layout"] = preview_layout()
    value["document"]["revision_id"] = str(uuid.uuid4())
    seen: list[PrintCreate] = []

    async def prepare(request, current, identity, body, *, pinned_layout=None):
        seen.append(body)
        assert pinned_layout == value["layout"]
        return copy.deepcopy(value)

    monkeypatch.setattr(purchase_print, "prepare", prepare)
    await purchase_print.reauthorize(None, None, uuid.uuid4(), value)
    assert str(seen[0].layout_preview.version_id) == value["layout"]["version_id"]


# --- the real browser (selected with -k real_chromium) ---


async def test_real_chromium_roll_and_picture(tmp_path):
    from pypdf import PdfReader

    from vouchers.config import PrintRuntime
    from vouchers.tasks.print_child import render

    settings = PrintRuntime(database_url="sqlite+aiosqlite:///:memory:")
    executable = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    value = snapshot()
    value["layout"] = roll()
    value["layout"]["layout_definition"]["sections"][0]["elements"].append(
        element("IMAGE", 30, 0, 20, 10, asset_id=ASSET)
    )
    value["layout"]["assets"] = [resolved()]
    data = await render(
        value,
        executable if executable.is_file() else None,
        sandbox=settings.print_chromium_sandbox,
    )
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert round(float(box.width) / 72 * 25.4) == 80
    assert 100 < float(box.height) / 72 * 25.4 < 400  # as long as the content, not 5 metres
    assert reader.pages[0].images, "the picture is embedded in the PDF"
    assert "Purchase voucher" in reader.pages[0].extract_text()


def test_a_webp_picture_is_embedded_and_a_fake_one_refused():
    webp = b"RIFF\x10\x00\x00\x00WEBPVP8 " + bytes(8)
    value_layout = with_logo(data=webp)
    value_layout["assets"] = [resolved(webp, mime_type="image/webp")]
    assert "data:image/webp;base64," in printed(value_layout)
    fake = b"RIFF\x10\x00\x00\x00JUNKVP8 " + bytes(8)
    value_layout["assets"] = [resolved(fake, mime_type="image/webp")]
    with pytest.raises(ValidationFailedError, match="does not match its evidence"):
        printed(value_layout)


def test_a_picture_with_an_unknown_fit_or_never_resolved_is_refused():
    value_layout = with_logo()
    value_layout["layout_definition"]["sections"][0]["elements"][-1]["image_fit"] = "tile"
    with pytest.raises(ValidationFailedError, match="picture fit"):
        printed(value_layout)
    # The renderer's own guard behind the manifest: a picture it was not given never prints.
    from test_purchase_print import snapshot as fresh

    from vouchers.domain.canvas_print import Facts, element_html

    value = fresh()
    value["layout"] = with_logo()
    value["layout"]["assets"] = []
    facts = Facts(value, display_config(), "Not allocated")
    with pytest.raises(ValidationFailedError, match="not resolved"):
        element_html(element("IMAGE", 0, 0, 5, 5, asset_id=ASSET), facts)


def display_config():
    from billing_platform.display import DisplayConfiguration

    return DisplayConfiguration.model_validate(snapshot()["display"])


def test_an_upper_case_asset_id_still_finds_its_picture():
    value_layout = with_logo()
    value_layout["layout_definition"]["sections"][0]["elements"][-1]["asset_id"] = ASSET.upper()
    assert problems(value_layout, PURCHASE) == []
    assert "data:image/png;base64," in printed(value_layout)


def test_copies_on_a_roll_follow_each_other_down_one_strip():
    value_layout = roll()
    value_layout["layout_definition"]["print_options"]["copies"] = [
        "ORIGINAL_FOR_RECIPIENT",
        "TRIPLICATE_FOR_SUPPLIER",
    ]
    html = printed(value_layout)
    css = html.split("<style>")[1].split("</style>")[0]
    assert css.index(".canvas-copy + .canvas-copy { break-before: page; }") < css.index(
        ".canvas-copy + .canvas-copy { break-before: auto;"
    )


def test_an_unavailable_picture_names_an_operator_fault():
    value_layout = with_logo()
    value_layout["assets"] = [{"asset_id": ASSET, "status": "UNAVAILABLE"}]
    with pytest.raises(ValidationFailedError, match="ask your administrator"):
        printed(value_layout)


def pictured(preview):
    return as_preview(preview) | {"assets": [resolved()]}


async def test_a_preview_with_pictures_also_needs_design_asset_read(
    client, prefix, app, tmp_path, monkeypatch
):
    from conftest import PERMISSIONS

    result, *_ = await preview_request(
        client, prefix, app, tmp_path, monkeypatch, PERMISSIONS | {"design.template.read"}, pictured
    )
    assert result.status_code == 403


async def test_a_preview_with_pictures_prints_for_an_asset_reader(
    client, prefix, app, tmp_path, monkeypatch
):
    from conftest import PERMISSIONS

    granted = PERMISSIONS | {"design.template.read", "design.asset.read"}
    result, *_ = await preview_request(
        client, prefix, app, tmp_path, monkeypatch, granted, pictured
    )
    assert result.status_code == 202, result.text
