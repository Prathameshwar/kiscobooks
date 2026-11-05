"""The Chromium sandbox is always on, except by an explicit, local-development-only switch.

Production keeps the sandbox. Disabling it exists only so the Purchase print can be exercised on a
developer machine whose sandboxed browser cannot start; it can never be enabled for staging or
production, is never exposed by an API, and is logged loudly whenever it is in effect.
No browser is started: Playwright and the renderer process are replaced by fakes.
"""

import json
import logging

import pytest
from billing_platform.errors import ConflictError
from pydantic import ValidationError
from test_purchase_print import snapshot

from vouchers.config import PrintRuntime, chromium_sandbox
from vouchers.tasks import print_child, print_worker

URL = "sqlite+aiosqlite:///:memory:"
SWITCH = "VOUCHERS_PRINT_CHROMIUM_SANDBOX"
ENVIRONMENT = "VOUCHERS_ENVIRONMENT"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """A developer's own shell may already carry the local switch; tests set what they need."""
    monkeypatch.delenv(SWITCH, raising=False)
    monkeypatch.delenv(ENVIRONMENT, raising=False)


def runtime(**values) -> PrintRuntime:
    return PrintRuntime(database_url=URL, **values)


def test_the_sandbox_is_on_by_default_in_a_production_default_environment():
    settings = runtime()
    assert settings.print_chromium_sandbox is True
    assert settings.environment == "production"
    assert chromium_sandbox(settings) is True


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_the_off_switch_is_refused_outside_development(environment):
    with pytest.raises(ValidationError, match="development"):
        runtime(environment=environment, print_chromium_sandbox=False)


def test_the_off_switch_is_refused_when_the_environment_is_not_declared():
    with pytest.raises(ValidationError, match="development"):
        runtime(print_chromium_sandbox=False)


def test_an_unknown_environment_is_refused_not_treated_as_local():
    with pytest.raises(ValidationError):
        runtime(environment="local", print_chromium_sandbox=False)
    with pytest.raises(ValidationError):
        runtime(environment="dev")


def test_the_off_switch_is_allowed_in_development():
    settings = runtime(environment="development", print_chromium_sandbox=False)
    assert chromium_sandbox(settings) is False


def test_development_alone_keeps_the_sandbox_on():
    assert chromium_sandbox(runtime(environment="development")) is True


def test_the_switch_and_environment_come_from_the_process_environment(monkeypatch):
    monkeypatch.setenv(SWITCH, "false")
    with pytest.raises(ValidationError, match="development"):
        PrintRuntime(database_url=URL)
    monkeypatch.setenv(ENVIRONMENT, "production")
    with pytest.raises(ValidationError, match="development"):
        PrintRuntime(database_url=URL)
    monkeypatch.setenv(ENVIRONMENT, "development")
    assert chromium_sandbox(PrintRuntime(database_url=URL)) is False


def test_the_refusal_never_echoes_configuration_values(monkeypatch):
    monkeypatch.setenv(SWITCH, "false")
    monkeypatch.setenv(ENVIRONMENT, "production")
    with pytest.raises(ValidationError) as error:
        PrintRuntime(database_url="sqlite+aiosqlite:///secret-database-name")
    assert "secret-database-name" not in str(error.value)


def test_a_switch_flipped_after_validation_is_still_refused_at_render_time():
    settings = runtime()
    settings.print_chromium_sandbox = False  # settings are mutable after construction
    with pytest.raises(ConflictError, match="sandbox"):
        chromium_sandbox(settings)


def test_the_switch_is_not_part_of_any_api_document():
    from pathlib import Path

    openapi = (Path(__file__).parents[1] / "openapi.json").read_text("utf-8").lower()
    assert "sandbox" not in openapi and "chromium" not in openapi


async def test_the_api_exposes_no_sandbox_setting(client):
    from conftest import headers

    for path in ("/health/live", "/health/ready", "/openapi.json"):
        response = await client.get(path, headers=headers())
        assert "sandbox" not in response.text.lower()


# --- the launch arguments ------------------------------------------------------------------------


class Page:
    def set_default_timeout(self, value):
        pass

    async def set_content(self, html, **options):
        pass

    async def pdf(self, **options):
        return b"%PDF-1.7 fake"


class Context:
    async def route(self, pattern, handler):
        pass

    async def new_page(self):
        return Page()


class Browser:
    async def new_context(self, **options):
        return Context()

    async def close(self):
        pass


def launches(monkeypatch) -> list[dict]:
    seen: list[dict] = []

    class Chromium:
        async def launch(self, **options):
            seen.append(options)
            return Browser()

    class Runtime:
        chromium = Chromium()

    class Manager:
        async def __aenter__(self):
            return Runtime()

        async def __aexit__(self, *error):
            return None

    monkeypatch.setattr(print_child, "async_playwright", Manager)
    return seen


async def test_the_browser_launches_sandboxed_unless_told_otherwise(monkeypatch):
    seen = launches(monkeypatch)
    await print_child.render(snapshot())
    await print_child.render(snapshot(), sandbox=True)
    assert [options["chromium_sandbox"] for options in seen] == [True, True]


async def test_the_browser_launch_reflects_the_off_switch(monkeypatch):
    seen = launches(monkeypatch)
    await print_child.render(snapshot(), sandbox=False)
    assert seen[0]["chromium_sandbox"] is False
    assert not any("sandbox" in str(value) for key, value in seen[0].items() if key == "args")


class FakeProcess:
    pid = 0
    returncode = 0

    def __init__(self, sink: list[dict]) -> None:
        self.sink = sink

    def communicate(self, payload, timeout=None):
        self.sink.append(json.loads(payload))
        return b"%PDF-1.7 rendered %%EOF", b""

    def poll(self):
        return 0


def fake_renderer(monkeypatch) -> list[dict]:
    payloads: list[dict] = []
    monkeypatch.setattr(
        print_worker.subprocess, "Popen", lambda *args, **options: FakeProcess(payloads)
    )
    return payloads


def test_the_parent_hands_the_child_exactly_the_validated_switch(monkeypatch):
    payloads = fake_renderer(monkeypatch)
    print_worker.render(runtime(), snapshot())
    print_worker.render(
        runtime(environment="development", print_chromium_sandbox=False), snapshot()
    )
    assert [payload["chromium_sandbox"] for payload in payloads] == [True, False]


def test_a_child_payload_that_is_not_an_explicit_false_keeps_the_sandbox():
    for payload in (
        {},
        {"chromium_sandbox": None},
        {"chromium_sandbox": 0},
        {"chromium_sandbox": "false"},
    ):
        assert print_child.sandbox_requested(payload) is True
    assert print_child.sandbox_requested({"chromium_sandbox": False}) is False


def test_a_disabled_sandbox_is_logged_as_a_warning_on_every_render(monkeypatch, caplog):
    fake_renderer(monkeypatch)
    settings = runtime(environment="development", print_chromium_sandbox=False)
    with caplog.at_level(logging.WARNING, logger="vouchers.print"):
        print_worker.render(settings, snapshot())
        print_worker.render(settings, snapshot())
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert "sandbox" in warnings[0].getMessage().lower()
    assert "DISABLED" in warnings[0].getMessage() and "development" in warnings[0].getMessage()


def test_a_sandboxed_render_logs_no_sandbox_warning(monkeypatch, caplog):
    fake_renderer(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="vouchers.print"):
        print_worker.render(runtime(), snapshot())
    assert not caplog.records


def test_startup_warns_when_the_sandbox_is_off(caplog):
    from vouchers.tasks.print_dispatcher import announce_sandbox

    with caplog.at_level(logging.WARNING, logger="vouchers.print"):
        announce_sandbox(runtime())
        assert not caplog.records
        announce_sandbox(runtime(environment="development", print_chromium_sandbox=False))
    assert len(caplog.records) == 1 and "DISABLED" in caplog.records[0].getMessage()
