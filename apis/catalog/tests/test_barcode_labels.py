"""Rendered labels encode the stored value without adding an untrusted SVG payload."""

from catalog.domain.barcode_labels import render_label


def test_code128_and_gtin_labels_are_svg() -> None:
    for value, kind in (
        ("IAGDAFXTPXN7EJI5DY22PWPKVYU", "CODE128"),
        ("036000291452", "GTIN"),
        ("4006381333931", "GTIN"),
        ("00036000291452", "GTIN"),
    ):
        svg = render_label(value, kind)
        assert b"<svg" in svg and b"</svg>" in svg


def test_qr_label_does_not_embed_untrusted_markup() -> None:
    svg = render_label("<script>alert(1)</script>", "QR")
    assert b"<svg" in svg and b"<script>" not in svg
