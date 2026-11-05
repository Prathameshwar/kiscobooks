"""Local browser -> production proxy -> production Notification API journeys.

Run with an isolated pinned Playwright installation; Chrome must already be installed.
Disposable SQLite data and screenshots live under .tools, never application storage.
"""

import contextlib
import json
import os
import socket
import sys
sys.stdout.reconfigure(encoding="utf-8")
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[5]
CONSOLE = ROOT / "mfes/apps/console"
HERE = Path(__file__).resolve().parent
OUTPUT = ROOT / ".tools" / ("notification-ui-browser-" + uuid.uuid4().hex)
OUTPUT.mkdir(parents=True)


def port():
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        return available.getsockname()[1]


api_port, web_port = port(), port()
environment = {**os.environ, "NOTIFICATION_E2E_API_PORT": str(api_port), "NOTIFICATION_E2E_WEB_PORT": str(web_port),
               "NOTIFICATION_E2E_DATABASE": "sqlite+aiosqlite:///" + (OUTPUT / "fixture.db").as_posix()}
base = f"http://127.0.0.1:{web_port}"
api = f"http://127.0.0.1:{api_port}"
processes, logs = [], []
flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def launch(arguments, directory, name):
    output = (OUTPUT / name).open("w", encoding="utf-8")
    logs.append(output)
    process = subprocess.Popen(arguments, cwd=directory, env=environment, stdout=output, stderr=subprocess.STDOUT, creationflags=flags)
    processes.append(process)
    return process


def ready(url):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("A fixture service exited before it was ready")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "text/html"}), timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            time.sleep(0.2)
    raise TimeoutError("Fixture service did not become ready")


def save(page, title):
    page.get_by_role("dialog", name=title, exact=True).get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_role("dialog", name=title, exact=True)).not_to_be_visible()


def area(page, name):
    page.get_by_role("navigation", name="Notification areas").get_by_role("link", name=name, exact=True).click()


def review_areas(page):
    sections = ("", "channels", "providers", "templates", "assignments", "routing", "recipients",
                "consent", "suppressions", "requests", "deliveries", "receipts", "recovery")
    errors = []
    def capture_error(error):
        errors.append(str(error))
    page.on("pageerror", capture_error)
    for owner in ("tenant", "platform"):
        root = "/settings/notifications" if owner == "tenant" else "/platform/notifications"
        for section in sections:
            page.goto(base + root + ("/" + section if section else ""), wait_until="domcontentloaded", timeout=60000)
            expect(page.get_by_role("heading", level=1, name="Notifications" if owner == "tenant" else "Platform notifications", exact=True)).to_be_visible()
            expect(page.get_by_role("navigation", name="Notification areas").get_by_role("link")).to_have_count(13)
            expect(page.locator('[aria-busy="true"]')).to_have_count(0)
            expect(page.get_by_role("alert")).to_have_count(0)
            assert not errors, "Notification browser runtime error: " + str(errors)
            page.screenshot(path=str(OUTPUT / (owner + "-area-" + (section or "overview") + ".png")), full_page=True)
            print("Reviewed " + owner + " " + (section or "overview"), flush=True)
    page.remove_listener("pageerror", capture_error)


def journey(page, owner, channel):
    prefix = "/platform/notifications" if owner == "platform" else "/settings/notifications"
    realm = owner.upper()
    purpose = "platform / staff / alert" if owner == "platform" else "voucher / shared"
    key = f"{owner}-{channel}"
    page.goto(base + ("/platform" if owner == "platform" else "/settings"), wait_until="domcontentloaded", timeout=60000)
    page.get_by_role("link", name="Platform notifications" if owner == "platform" else "Notifications", exact=True).click()
    area(page, "Providers and senders")
    page.get_by_role("button", name="Add provider", exact=True).click()
    page.get_by_label("Provider", exact=True).select_option({"email": "ses", "sms": "twilio", "whatsapp": "meta"}[channel])
    page.get_by_label("Account key", exact=True).fill(key)
    page.get_by_label("Account name", exact=True).fill(key + " transport")
    page.get_by_label("Credential binding", exact=True).select_option("env:" + realm + "_PROVIDER")
    if channel == "email":
        page.get_by_label("AWS region", exact=True).fill("us-east-1")
        page.get_by_label("SES receipt SNS topic ARN", exact=True).fill("arn:aws:sns:us-east-1:123456789012:notification-test")
    else:
        page.get_by_label("Callback signature binding", exact=True).select_option("env:" + realm + "_CALLBACK")
    if channel == "whatsapp":
        page.get_by_label("WhatsApp verification-token binding", exact=True).select_option("env:" + realm + "_CALLBACK")
    save(page, "Add provider")
    page.get_by_role("link", name=key + " transport", exact=True).click()
    provider_id = page.url.split("/")[-1]
    page.get_by_role("button", name="Validate provider", exact=True).click()
    expect(page.get_by_text("completed", exact=True)).to_be_visible()
    expect(page.get_by_text("active", exact=True).first).to_be_visible()
    page.get_by_role("link", name="Manage sender identities", exact=True).click()
    page.get_by_role("button", name="Add sender", exact=True).click()
    page.get_by_label("Sender key", exact=True).fill("primary")
    page.get_by_label("Sender name", exact=True).fill(key + " sender")
    label, sender = {"email": ("Sender email identity", "noreply@example.invalid"), "sms": ("SMS sender number (E.164)", "+15557654321"), "whatsapp": ("WhatsApp phone number ID", "fixture-phone-id")}[channel]
    page.get_by_label(label, exact=True).fill(sender)
    save(page, "Add sender")
    page.get_by_role("link", name=key + " sender", exact=True).click()
    page.get_by_role("button", name="Verify sender", exact=True).click()
    expect(page.get_by_text("completed", exact=True)).to_be_visible()
    expect(page.get_by_text("verified", exact=True).first).to_be_visible()
    area(page, "Channels")
    if owner == "tenant":
        expect(page.get_by_role("button", name="Disable " + channel, exact=True)).to_be_visible()
        page.get_by_role("button", name="Disable " + channel, exact=True).click()
        page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Enable " + channel, exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.get_by_role("button", name="Disable " + channel, exact=True)).to_be_visible()
    area(page, "Templates")
    page.get_by_role("button", name="Add template", exact=True).click()
    page.get_by_label("Registered purpose", exact=True).select_option(label=purpose)
    page.get_by_label("Template key", exact=True).fill(key + "-template")
    page.get_by_label("Default language code", exact=True).fill("en")
    if owner == "tenant":
        page.get_by_role("button", name="Add variable", exact=True).click()
        page.get_by_label("Variable 1 name", exact=True).fill("message")
    save(page, "Add template")
    page.get_by_role("link", name=key + "-template", exact=True).click()
    page.get_by_role("button", name="Add channel and language", exact=True).click()
    page.get_by_label("Channel", exact=True).select_option(channel)
    save(page, "Add channel and language")
    page.get_by_role("table", name="Template channels and languages").get_by_role("link", name=channel, exact=True).click()
    page.get_by_role("button", name="Add content version", exact=True).click()
    page.get_by_label("Message text", exact=True).fill("Notice {{message}}")
    if channel == "email":
        page.get_by_label("Email subject", exact=True).fill("Staff alert")
    if channel == "whatsapp":
        page.get_by_label("Body variables in provider order", exact=True).fill("message")
    save(page, "Add content version")
    page.get_by_role("table", name="Content versions").get_by_role("link", name="1", exact=True).click()
    page.get_by_role("button", name="Preview with sample variables", exact=True).click()
    page.get_by_label("Sample message", exact=True).fill("A browser-tested alert")
    save(page, "Preview template")
    expect(page.get_by_label("Message preview").get_by_text("Notice A browser-tested alert", exact=True)).to_be_visible()
    if channel == "whatsapp":
        page.get_by_role("button", name="Connect provider template", exact=True).click()
        page.get_by_label("WhatsApp provider", exact=True).select_option(provider_id)
        page.get_by_label("Provider template ID", exact=True).fill("fixture-template")
        page.get_by_label("Provider template name", exact=True).fill("fixture_alert")
        save(page, "Connect provider template")
        page.get_by_role("button", name="Sync approval", exact=True).click()
        expect(page.get_by_text("completed", exact=True)).to_be_visible()
        expect(page.get_by_text("approved", exact=True).first).to_be_visible()
    page.get_by_role("button", name="Activate or schedule version", exact=True).click()
    save(page, "Activate version")
    area(page, "Purpose assignments")
    page.get_by_role("button", name="Assign a purpose", exact=True).click()
    page.get_by_label("Registered purpose", exact=True).select_option(label=purpose)
    page.get_by_label("Channel", exact=True).select_option(channel)
    page.get_by_label("Template", exact=True).select_option(label=key + "-template")
    save(page, "Assign a purpose")
    area(page, "Routing")
    page.get_by_role("button", name="Add route", exact=True).click()
    page.get_by_role("dialog", name="Add route", exact=True).get_by_label("Registered purpose", exact=True).select_option(label=purpose)
    page.get_by_role("dialog", name="Add route", exact=True).get_by_label("Channel", exact=True).select_option(channel)
    page.get_by_label("Provider account", exact=True).select_option(provider_id)
    page.get_by_label("Sender identity", exact=True).select_option(label=key + " sender")
    save(page, "Add route")
    page.get_by_role("button", name="Check policy", exact=True).click()
    page.get_by_role("dialog", name="Check effective policy", exact=True).get_by_label("Registered purpose", exact=True).select_option(label=purpose)
    page.get_by_role("dialog", name="Check effective policy", exact=True).get_by_label("Channel", exact=True).select_option(channel)
    save(page, "Check effective policy")
    expect(page.get_by_label("Effective policy result").locator("xpath=ancestor::div[@class='janso-card'][1]").get_by_text("ready", exact=True)).to_be_visible()
    result = page.request.post(api + "/__fixture__/send", headers={"X-Fixture-Control": "local-browser-test"}, data={"owner": owner, "channel": channel})
    assert result.status == 200, result.text()
    identities = result.json()
    page.goto(base + prefix + "/requests/" + identities["request_id"])
    expect(page.get_by_role("table", name="Channel planning outcomes").get_by_text(channel, exact=True)).to_be_visible()
    page.get_by_role("link", name="View deliveries for this request", exact=True).click()
    expect(page.get_by_role("table", name="Deliveries").get_by_text("delivered", exact=True)).to_be_visible()
    page.get_by_role("table", name="Deliveries").get_by_role("link").first.click()
    expect(page.get_by_role("table", name="Delivery attempts").get_by_text("accepted", exact=True)).to_be_visible()
    expect(page.get_by_role("table", name="Delivery events").get_by_text("delivered", exact=True)).to_be_visible()
    page.get_by_role("link", name="View masked recipient", exact=True).click()
    page.get_by_role("link", name="Manage consent", exact=True).click()
    page.get_by_role("button", name="Record consent evidence", exact=True).click()
    page.get_by_label("Consent state", exact=True).select_option("granted")
    page.get_by_label("Evidence reference", exact=True).fill("browser-evidence")
    save(page, "Record consent evidence")
    expect(page.get_by_role("table", name="Consent states").get_by_text("granted", exact=True)).to_be_visible()
    page.screenshot(path=str(OUTPUT / (key + ".png")), full_page=True)
    print(f"Passed {owner} {channel}: account -> sender -> template -> activation -> assignment -> routing -> source -> dispatch -> signed receipt -> history -> consent", flush=True)


try:
    launch([str(ROOT / "apis/notification/.venv/Scripts/python.exe"), str(HERE / "api.py")], ROOT / "apis/notification", "api.log")
    ready(api + "/health/live")
    launch(["node", str(HERE / "server.mjs")], CONSOLE, "web.log")
    ready(base + "/platform")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True, args=["--disable-background-networking"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, timezone_id="Asia/Kolkata")
        page = context.new_page()
        page.set_default_timeout(20000)
        expect.set_options(timeout=15000)
        def failed_response(response):
            if "/api/notifications" in response.url:
                payload = response.request.post_data_json
                if response.status >= 400:
                    print("Proxy response: " + str(response.status) + " " + payload.get("path", "") + " " + response.text()[:1000], flush=True)
        page.on("response", failed_response)
        review_areas(page)
        for realm, channel in [("platform", "email"), ("platform", "sms"), ("platform", "whatsapp"), ("tenant", "sms")]:
            journey(page, realm, channel)
        page.goto(base + "/platform/notifications/providers?profile=reader")
        expect(page.get_by_role("table", name="Provider accounts")).to_be_visible()
        expect(page.get_by_role("button", name="Add provider", exact=True)).not_to_be_visible()
        rejected = page.request.post(base + "/api/notifications", data={"service": "notification", "method": "POST", "path": "/v1/platform/provider-accounts", "body": {
            "key": "forbidden", "callback_key": uuid.uuid4().hex, "channel": "sms", "provider_key": "twilio",
            "display_name": "Read-only rejection", "credential_ref": "env:PLATFORM_PROVIDER", "callback_secret_ref": "env:PLATFORM_CALLBACK",
        }}, headers={"Origin": base})
        assert rejected.status == 403, rejected.text()
        page.goto(base + "/platform/notifications?profile=admin")
        expect(page.get_by_role("heading", name="Platform notifications", exact=True)).to_be_visible()
        for theme in ("light", "dark", "ledger"):
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Narrow layout overflow"
            page.screenshot(path=str(OUTPUT / ("overview-mobile-" + theme + ".png")), full_page=True)
        browser.close()
    print("Browser checks passed, including read-only API denial and narrow layouts in three themes.", flush=True)
    print("Artifacts: " + str(OUTPUT), flush=True)
except Exception:
    if "page" in locals():
        with contextlib.suppress(Exception):
            page.screenshot(path=str(OUTPUT / "failure.png"), full_page=True)
            (OUTPUT / "failure.html").write_text(page.content(), encoding="utf-8")
    for output in logs:
        output.flush()
    for name in ("api.log", "web.log"):
        print(name + ":\n" + (OUTPUT / name).read_text(encoding="utf-8")[-7000:], flush=True)
    raise
finally:
    for process in reversed(processes):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    for output in logs:
        output.close()
