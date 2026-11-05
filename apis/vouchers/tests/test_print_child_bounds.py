"""The renderer child bounds each of its own steps and exits by itself inside the parent's deadline.

No browser is used: Playwright is replaced by a fake whose steps hang on demand.
"""

import asyncio
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from test_purchase_print import snapshot

from vouchers.tasks import print_child

BOUND = 5  # seconds the test allows; the fake step bound below is far smaller
STEP = 0.3
SRC = str(Path(__file__).resolve().parents[1] / "src")


class Hung:
    async def __call__(self, *args, **options):
        await asyncio.sleep(3600)


class FakePage:
    def __init__(self, stuck: str) -> None:
        self.stuck = stuck

    def set_default_timeout(self, value):
        pass

    async def set_content(self, html, **options):
        if self.stuck == "set_content":
            await Hung()()

    async def pdf(self, **options):
        if self.stuck == "pdf":
            await Hung()()
        self.options = options
        return b"%PDF-1.7 fake"


class FakeContext:
    def __init__(self, stuck: str) -> None:
        self.stuck = stuck

    async def route(self, pattern, handler):
        pass

    async def new_page(self):
        if self.stuck == "new_page":
            await Hung()()
        return FakePage(self.stuck)


class FakeBrowser:
    def __init__(self, stuck: str) -> None:
        self.stuck = stuck
        self.closed = False

    async def new_context(self, **options):
        if self.stuck == "new_context":
            await Hung()()
        return FakeContext(self.stuck)

    async def close(self):
        self.closed = True
        if self.stuck == "close":
            await Hung()()


def install_fake(monkeypatch, stuck: str) -> FakeBrowser:
    browser = FakeBrowser(stuck)

    class Chromium:
        async def launch(self, **options):
            if stuck == "launch":
                await Hung()()
            return browser

    class Runtime:
        chromium = Chromium()

    class Manager:
        async def __aenter__(self):
            return Runtime()

        async def __aexit__(self, *error):
            return None

    monkeypatch.setattr(print_child, "async_playwright", Manager)
    monkeypatch.setattr(print_child, "STEP_SECONDS", STEP, raising=False)
    monkeypatch.setattr(print_child, "CLOSE_SECONDS", STEP, raising=False)
    return browser


@pytest.mark.parametrize("stuck", ["launch", "new_context", "new_page", "set_content", "pdf"])
async def test_a_stuck_step_fails_by_itself_well_inside_the_parent_deadline(monkeypatch, stuck):
    browser = install_fake(monkeypatch, stuck)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(print_child.render(snapshot()), BOUND)
    assert time.monotonic() - started < BOUND - 1, "the step had no bound of its own"
    if stuck != "launch":
        assert browser.closed, "the browser was not asked to close after the failure"


async def test_a_stuck_close_does_not_lose_or_block_a_finished_pdf(monkeypatch):
    install_fake(monkeypatch, "close")
    started = time.monotonic()
    data = await asyncio.wait_for(print_child.render(snapshot()), BOUND)
    assert data == b"%PDF-1.7 fake" and time.monotonic() - started < BOUND - 1


async def test_a_good_render_passes_the_page_identity_templates(monkeypatch):
    install_fake(monkeypatch, "none")
    captured = {}
    original = FakePage.pdf

    async def pdf(self, **options):
        captured.update(options)
        return await original(self, **options)

    monkeypatch.setattr(FakePage, "pdf", pdf)
    value = snapshot()
    value["document"]["issue_number"] = "PUR/26-27/00042"
    await print_child.render(value)
    assert captured["display_header_footer"] is True
    assert "PUR/26-27/00042" in captured["footer_template"]
    assert "Example Supplier" in captured["footer_template"]
    assert "BILL-123" in captured["footer_template"]


def test_the_watchdog_exits_the_process_when_the_deadline_passes():
    exits = []
    fired = threading.Event()

    def record(code):
        exits.append(code)
        fired.set()

    watchdog = print_child.arm_watchdog(0.2, record)
    assert fired.wait(5) and exits == [print_child.EXIT_DEADLINE]
    assert watchdog is not None


def test_a_disarmed_watchdog_never_fires():
    exits = []
    watchdog = print_child.arm_watchdog(0.3, exits.append)
    watchdog.disarm()
    time.sleep(0.8)
    assert exits == []


def test_a_watchdog_that_already_fired_is_not_undone_by_a_late_disarm():
    exits = []
    watchdog = print_child.arm_watchdog(0.1, exits.append)
    time.sleep(0.6)
    watchdog.disarm()
    assert exits == [print_child.EXIT_DEADLINE]


FAKE_CHILD = """
import asyncio, sys
sys.path.insert(0, {src!r})
from vouchers.tasks import print_child

class Chromium:
    async def launch(self, **options):
        await asyncio.sleep(3600)

class Runtime:
    chromium = Chromium()

class Manager:
    async def __aenter__(self):
        return Runtime()

    async def __aexit__(self, *error):
        await asyncio.sleep({exit_sleep})

print_child.async_playwright = Manager
print_child.STEP_SECONDS = {step}
print_child.main()
"""


def run_child(step: float, deadline: int, exit_sleep: int) -> tuple[int, bytes, float]:
    """Real process, real os._exit: only Playwright is faked; launch hangs, and so may its exit."""
    script = FAKE_CHILD.format(src=SRC, step=step, exit_sleep=exit_sleep)
    payload = json.dumps({"snapshot": snapshot(), "executable": None, "deadline_seconds": deadline})
    started = time.monotonic()
    process = subprocess.Popen(  # noqa: S603 -- fixed fake script, no shell.
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        output, _ = process.communicate(payload.encode(), timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        pytest.fail("the child never exited on its own deadline")
    return process.returncode, output, time.monotonic() - started


def test_a_hung_child_process_exits_non_zero_on_its_own_deadline():
    code, output, seconds = run_child(3600, deadline=1, exit_sleep=3600)
    assert code == print_child.EXIT_DEADLINE and output == b"" and seconds < 60


def test_a_timed_out_step_ends_the_child_with_the_deadline_status():
    # The step bound fires well before the 50 s watchdog; the status is still "deadline".
    code, output, seconds = run_child(0.3, deadline=50, exit_sleep=0)
    assert code == print_child.EXIT_DEADLINE and output == b"" and seconds < 45


FAKE_PRODUCER = """
import asyncio, sys
sys.path.insert(0, {src!r})
from vouchers.tasks import print_child

class Page:
    def set_default_timeout(self, value):
        pass

    async def set_content(self, html, **options):
        pass

    async def pdf(self, **options):
        return b"%PDF-1.7 finished"

class Context:
    async def route(self, pattern, handler):
        pass

    async def new_page(self):
        return Page()

class Browser:
    async def new_context(self, **options):
        return Context()

    async def close(self):
        await asyncio.sleep({close_sleep})

class Chromium:
    async def launch(self, **options):
        return Browser()

class Runtime:
    chromium = Chromium()

class Manager:
    async def __aenter__(self):
        return Runtime()

    async def __aexit__(self, *error):
        await asyncio.sleep({exit_sleep})

print_child.async_playwright = Manager
print_child.TEARDOWN_SECONDS = 0.5
print_child.CLOSE_SECONDS = 0.5
print_child.main()
"""


def run_script(script: str, deadline: int) -> tuple[int, bytes, float]:
    payload = json.dumps({"snapshot": snapshot(), "executable": None, "deadline_seconds": deadline})
    started = time.monotonic()
    process = subprocess.Popen(  # noqa: S603 -- fixed fake script, no shell.
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        output, _ = process.communicate(payload.encode(), timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        pytest.fail("the child never exited")
    return process.returncode, output, time.monotonic() - started


@pytest.mark.parametrize(
    ("close_sleep", "exit_sleep"), [(0, 3600), (3600, 0), (3600, 3600)], ids=lambda v: str(v)
)
def test_a_finished_pdf_survives_a_hung_browser_or_driver_teardown(close_sleep, exit_sleep):
    """The deadline (3 s) passes while the driver teardown hangs: the PDF still wins."""
    script = FAKE_PRODUCER.format(src=SRC, close_sleep=close_sleep, exit_sleep=exit_sleep)
    code, output, seconds = run_script(script, deadline=3)
    assert output == b"%PDF-1.7 finished", "the finished PDF was lost"
    assert code == 0, f"a finished render exited with status {code}"
    assert seconds < 40


class SlowBuffer(io.BytesIO):
    """A stdout whose write takes a while, like a pipe the parent is slow to drain."""

    def __init__(self, delay: float = 0.0) -> None:
        super().__init__()
        self.delay = delay

    def write(self, data):
        time.sleep(self.delay)
        return super().write(data)


def run_main(monkeypatch, render, deadline=30, stdout=None, exits=None):
    """Run `main` in-process with fake stdin/stdout and a recording exit function."""
    payload = json.dumps({"snapshot": snapshot(), "executable": None, "deadline_seconds": deadline})
    stdout = stdout if stdout is not None else io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload.encode())))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=stdout))
    monkeypatch.setattr(print_child, "render", render)
    exits = exits if exits is not None else []
    print_child.main(exits.append)
    return exits, stdout.getvalue()


def producing(data=b"%PDF-1.7 fake", before=0.0, linger=0.0, then_fail=None):
    """A fake renderer that hands over its PDF like the real one, then lingers or fails."""

    async def render(snapshot, executable=None, deliver=None):
        await asyncio.sleep(before)
        if deliver is not None:
            deliver(data)
        await asyncio.sleep(linger)  # driver teardown after the PDF exists
        if then_fail is not None:
            raise then_fail
        return data

    return render


@pytest.mark.parametrize("error", [TimeoutError("step"), PlaywrightTimeoutError("playwright step")])
def test_main_reports_any_timeout_with_the_deadline_status(monkeypatch, error):
    async def stuck(snapshot, executable=None, deliver=None):
        raise error

    exits, output = run_main(monkeypatch, stuck)
    assert exits == [print_child.EXIT_DEADLINE] and output == b""


def test_main_writes_the_pdf_flushes_and_exits_cleanly(monkeypatch):
    exits, output = run_main(monkeypatch, producing())
    assert exits == [0] and output == b"%PDF-1.7 fake"


def test_the_deadline_cannot_fire_once_the_pdf_exists(monkeypatch):
    # The PDF is ready at 0.2 s; teardown lingers to 1.8 s, well past the 1 s deadline.
    exits, output = run_main(monkeypatch, producing(before=0.2, linger=1.6), deadline=1)
    assert output == b"%PDF-1.7 fake"
    assert exits == [0], f"a finished render was reported as {exits}"


def test_a_deadline_during_a_slow_write_does_not_lose_the_finished_pdf(monkeypatch):
    # The PDF is ready at 0.9 s, 0.1 s before the deadline; the write then takes 1.5 s.
    exits, output = run_main(
        monkeypatch, producing(before=0.9), deadline=1, stdout=SlowBuffer(delay=1.5)
    )
    assert output == b"%PDF-1.7 fake"
    assert exits == [0], f"a finished render was reported as {exits}"


def test_a_driver_error_after_the_pdf_was_delivered_is_not_a_failure(monkeypatch):
    exits, output = run_main(monkeypatch, producing(then_fail=RuntimeError("driver crashed")))
    assert exits == [0] and output == b"%PDF-1.7 fake"


def test_an_error_before_any_pdf_is_still_a_failure(monkeypatch):
    async def broken(snapshot, executable=None, deliver=None):
        raise RuntimeError("browser crashed")

    with pytest.raises(RuntimeError, match="browser crashed"):
        run_main(monkeypatch, broken)


def test_a_failed_hand_over_is_a_failure_and_stays_bounded(monkeypatch):
    monkeypatch.setattr(print_child, "TEARDOWN_SECONDS", 0.2)
    exits: list[int] = []

    class Broken(io.BytesIO):
        def write(self, data):
            raise BrokenPipeError("the parent closed the pipe")

    with pytest.raises(BrokenPipeError):
        run_main(monkeypatch, producing(), stdout=Broken(), exits=exits)
    time.sleep(0.8)
    # The deadline was disarmed for the hand-over; a bounded guard still ends it, as failed.
    assert exits == [1]
