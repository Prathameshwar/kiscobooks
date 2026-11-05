"""Bounded vector output for protected product-code labels."""

# python-barcode 0.16.1 has no py.typed marker; rendered outputs are exercised in tests.
from barcode import EAN8, EAN13, UPCA, Code128, get  # type: ignore[import-untyped]
from barcode.writer import SVGWriter  # type: ignore[import-untyped]
from billing_platform.errors import ValidationFailedError
from qrcode import make
from qrcode.image.svg import SvgPathImage

from catalog.domain.product_authoring import validate_barcode


def render_label(value: str, symbology: str) -> bytes:
    validate_barcode(value, symbology)
    if symbology == "QR":
        output: bytes = make(value, image_factory=SvgPathImage).to_string()
    else:
        writer = SVGWriter()
        if symbology == "CODE128":
            code = Code128(value, writer=writer)
        elif symbology == "GTIN":
            if len(value) == 8:
                code = EAN8(value[:-1], writer=writer)
            elif len(value) == 12:
                code = UPCA(value[:-1], writer=writer)
            elif len(value) == 13:
                code = EAN13(value[:-1], writer=writer)
            else:
                code = get("ean14", value[:-1], writer=writer)
            if code.get_fullcode() != value:
                raise ValidationFailedError("GTIN label does not match the stored check digit")
        else:
            raise ValidationFailedError("unsupported barcode label type")
        output = code.render({"write_text": True, "quiet_zone": 6.5})
    if len(output) > 512 * 1024:
        raise ValidationFailedError("barcode label exceeds output limit")
    return output
