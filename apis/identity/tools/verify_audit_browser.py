"""Browser half of verify_accounting_audit.py; credentials stay in the process environment."""

import json
import os
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    origin = os.environ["AUDIT_PROOF_ORIGIN"]
    artifacts = Path(os.environ["AUDIT_PROOF_ARTIFACTS"])
    catalog = os.environ.get("AUDIT_PROOF_SERVICE") == "catalog"
    entity = "catalog.unit_of_measure" if catalog else "accounting.party"
    field = "quantity_increment" if catalog else "country_code"
    old, new = ("1.0000", "2.0000") if catalog else ("IN", "US")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1440, "height": 1000}
        )
        context.add_cookies(
            [
                {
                    "name": "next-auth.session-token",
                    "value": os.environ["AUDIT_PROOF_COOKIE"],
                    "url": origin,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        try:
            page.goto(
                origin
                + "/audit?company_id="
                + os.environ["AUDIT_PROOF_COMPANY"]
                + "&entity_type="
                + entity,
                wait_until="networkidle",
                timeout=90000,
            )
            expect(page.get_by_role("heading", name="Audit log")).to_be_visible(timeout=30000)
            # The dev API route compiles on its first request; allow the same bounded
            # startup budget as navigation before clicking the actual live update row.
            page.get_by_role(
                "button", name=re.compile(r"^Show details for " + re.escape(entity) + r"\.update")
            ).click(timeout=90000)
            expect(page.get_by_text(field, exact=True)).to_be_visible(timeout=60000)
            expect(page.get_by_text(old, exact=True)).to_be_visible()
            expect(page.get_by_text(new, exact=True)).to_be_visible()
            expect(page.get_by_text(re.compile(r"^Asha Rao \("))).to_be_visible(timeout=60000)
            page.screenshot(path=str(artifacts / "console-detail.png"), full_page=True)
            # Export is verified through its server response and the downloaded JSON.
            page.get_by_role("button", name="Export", exact=True).click()
            with page.expect_download(timeout=30000) as download:
                page.get_by_role("menuitem").filter(has_text="JSON").click()
            path = artifacts / "browser-export.json"
            download.value.save_as(path)
            data = json.loads(path.read_text())
            assert data["count"] >= 2 and all(e["entity_type"] == entity for e in data["events"])
            print("Browser list/detail/export passed")
        except Exception:
            page.screenshot(path=str(artifacts / "browser-failure.png"), full_page=True)
            (artifacts / "browser-failure.txt").write_text(
                page.locator("body").inner_text(), encoding="utf-8"
            )
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
