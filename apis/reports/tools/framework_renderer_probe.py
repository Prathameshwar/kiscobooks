"""Small packaging/renderer probe; output documents contain synthetic values only."""

import argparse
import importlib.metadata
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for distribution in ("xlsxwriter", "Jinja2", "weasyprint", "celery"):
        result[distribution] = {"version": importlib.metadata.version(distribution)}
    import xlsxwriter
    from jinja2 import Environment

    started = time.perf_counter()
    with xlsxwriter.Workbook(
        str(args.output_dir / "probe.xlsx"),
        {
            "constant_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
        },
    ) as book:
        sheet = book.add_worksheet("Register")
        heading = book.add_format({"bold": True})
        sheet.write_row(0, 0, ["Description", "Amount"], heading)
        sheet.freeze_panes(1, 0)
        for number in range(10_000):
            sheet.write_string(number + 1, 0, f"Synthetic row {number}")
            sheet.write_number(number + 1, 1, 100)
        sheet.autofilter(0, 0, 10_000, 1)
    result["xlsxwriter"] |= {
        "status": "PASS",
        "rows": 10_000,
        "seconds": time.perf_counter() - started,
    }
    template = Environment(autoescape=True).from_string(
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Report probe</title>"
        "<h1>{{ title }}</h1><table><thead><tr><th>Account</th><th>Amount</th></tr></thead>"
        "<tbody>{% for row in rows %}<tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td></tr>"
        "{% endfor %}</tbody></table></html>"
    )
    html = template.render(title="Report <probe>", rows=[("Cash", "100.00"), ("Revenue", "100.00")])
    (args.output_dir / "probe.html").write_text(html, encoding="utf-8")
    result["Jinja2"]["status"] = "PASS" if "&lt;probe&gt;" in html else "FAIL"
    started = time.perf_counter()
    try:
        from weasyprint import HTML

        HTML(string=html).write_pdf(args.output_dir / "probe.pdf")
        result["weasyprint"] |= {"status": "PASS", "seconds": time.perf_counter() - started}
    except (ImportError, OSError) as exc:
        result["weasyprint"] |= {
            "status": "DEPENDENCY_UNAVAILABLE",
            "error_type": type(exc).__name__,
        }
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, TableStyle

    started = time.perf_counter()
    document = SimpleDocTemplate(str(args.output_dir / "probe-reportlab.pdf"))
    table = LongTable(
        [["Account", "Amount"], *[[f"Synthetic row {n}", "100.00"] for n in range(2000)]],
        colWidths=[330, 100],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ]
        )
    )
    document.build([Paragraph("Report packaging probe", getSampleStyleSheet()["Title"]), table])
    result["reportlab"] = {
        "version": importlib.metadata.version("reportlab"),
        "status": "PASS",
        "rows": 2000,
        "seconds": time.perf_counter() - started,
    }
    result["celery"]["status"] = "INSTALLED; worker execution checked separately"
    (args.output_dir / "result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
