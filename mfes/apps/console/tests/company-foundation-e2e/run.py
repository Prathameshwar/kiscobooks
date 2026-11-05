"""Production company shell/proxy browser checks with fixture upstream services."""
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
OUTPUT = ROOT / ".tools" / ("company-foundation-browser-" + uuid.uuid4().hex)
OUTPUT.mkdir(parents=True)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"
log = (OUTPUT / "web.log").open("w", encoding="utf-8")
process = subprocess.Popen(["node", str(HERE / "server.mjs")], cwd=ROOT / "mfes/apps/console",
    env={**os.environ, "COMPANY_E2E_PORT": str(port)}, stdout=log, stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
try:
    deadline = time.monotonic() + 60
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(base, headers={"Accept": "text/html"}), timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            if time.monotonic() > deadline or process.poll() is not None:
                raise RuntimeError("Browser fixture failed to start")
            time.sleep(0.2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, timezone_id="Asia/Kolkata")
        page = context.new_page()
        page.set_default_timeout(20000)
        page.goto(base + "/settings/readiness")
        expect(page.get_by_role("heading", name="Company readiness", exact=True)).to_be_visible()
        expect(page.get_by_text("Opening balances have not been finalised.", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Reports", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Administration", exact=True)).not_to_be_visible()
        before = {cookie["name"]: cookie["value"] for cookie in context.cookies()}
        page.get_by_label("Fixture protected draft", exact=True).fill("Protected company A draft")
        page.get_by_role("button", name="Switch company", exact=False).click()
        page.get_by_role("option", name="Company B", exact=False).click()
        expect(page.get_by_text("Save or discard unsaved changes before changing company or financial year.", exact=True)).to_be_visible()
        after = {cookie["name"]: cookie["value"] for cookie in context.cookies()}
        assert before == after, "Blocked editor switch changed context cookies"
        expect(page.get_by_text("Setup evidence for Company A", exact=False)).to_be_visible()
        page.get_by_role("button", name="Save fixture draft", exact=True).click()
        page.get_by_label("Fixture draft to verify context reset").fill("Unsaved company A fixture")
        page.get_by_role("button", name="Switch company", exact=False).click()
        page.get_by_role("option", name="Company B", exact=False).click()
        expect(page.get_by_text("Setup evidence for Company B", exact=False)).to_be_visible()
        expect(page.get_by_role("link", name="Reports", exact=True)).not_to_be_visible()
        expect(page.get_by_text("USD", exact=True)).to_be_visible()
        expect(page.get_by_label("Fixture draft to verify context reset")).to_have_value("")
        page.get_by_role("button", name="Switch company", exact=False).click()
        page.get_by_role("option", name="Company A", exact=False).click()
        expect(page.get_by_role("link", name="Reports", exact=True)).to_be_visible()
        page.get_by_label("Fixture draft to verify context reset").fill("Prior-year fixture")
        page.get_by_role("button", name="Switch financial year", exact=False).click()
        page.get_by_role("option", name="2025-26", exact=False).click()
        expect(page.get_by_text("Setup evidence for Company A · 2025-26", exact=True)).to_be_visible()
        expect(page.get_by_label("Fixture draft to verify context reset")).to_have_value("")
        before = {cookie["name"]: cookie["value"] for cookie in context.cookies()}
        denied = page.request.post(base + "/api/company-context", data={"company": "01990000-0000-7000-8000-000000000099"}, headers={"Origin": base})
        assert denied.status == 403
        after = {cookie["name"]: cookie["value"] for cookie in context.cookies()}
        assert before["janso-company"] == after["janso-company"]
        assert before["janso-fiscal-year"] == after["janso-fiscal-year"]
        print("Passed unsaved-editor switch protection, company A/B switch, permission refresh, year verification, workspace reset and denied-selection cookie preservation", flush=True)
        page.goto(base + "/settings/readiness?profile=reader")
        expect(page.get_by_role("heading", name="Company readiness", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Switch financial year", exact=False)).not_to_be_visible()
        expect(page.get_by_text("INR", exact=True)).not_to_be_visible()
        page.goto(base + "/settings/readiness?profile=tenant")
        expect(page.get_by_role("link", name="Administration", exact=True)).to_be_visible()
        expect(page.get_by_text("Opening balances have not been finalised.", exact=True)).to_be_visible()
        page.screenshot(path=str(OUTPUT / "company-readiness-desktop.png"), full_page=True)
        for theme in ("light", "dark", "ledger"):
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
            assert page.evaluate("document.querySelector('.janso-main').scrollWidth <= document.querySelector('.janso-main').clientWidth"), "Company content overflow"
            page.screenshot(path=str(OUTPUT / ("company-readiness-mobile-" + theme + ".png")), full_page=True)
        page.get_by_text("Remaining setup responsibilities", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUTPUT / "company-readiness-mobile-lower.png"), full_page=True)
        browser.close()
    print("Company foundation browser checks passed. Artifacts: " + str(OUTPUT), flush=True)
except Exception:
    log.flush()
    print((OUTPUT / "web.log").read_text(encoding="utf-8")[-5000:], flush=True)
    raise
finally:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    log.close()
